#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/image.hpp"
#include <opencv2/opencv.hpp>
#include <memory>

class SimpleCameraPublisher : public rclcpp::Node {
public:
  SimpleCameraPublisher() : Node("camera_publisher"), publishing_(true) {
    // 默认摄像头设备
    camera_device_ = declare_parameter("camera_device", 0);
    // 发布频率 (Hz)
    publish_frequency_ = declare_parameter("publish_frequency", 30.0);
    // 图像宽度
    image_width_ = declare_parameter("image_width", 640);
    // 图像高度
    image_height_ = declare_parameter("image_height", 480);

    // 创建图像发布者
    image_publisher_ = this->create_publisher<sensor_msgs::msg::Image>("camera/image_raw", 10);

    // 初始化摄像头
    if (!init_camera()) {
      RCLCPP_ERROR(this->get_logger(), "无法打开摄像头设备 /dev/video%d", camera_device_);
      return;
    }

    // 创建定时器来发布图像
    auto period = std::chrono::duration<double>(1.0 / publish_frequency_);
    timer_ = this->create_wall_timer(
      period, std::bind(&SimpleCameraPublisher::timer_callback, this));

    RCLCPP_INFO(this->get_logger(), "========================================");
    RCLCPP_INFO(this->get_logger(), "摄像头发布者节点已启动");
    RCLCPP_INFO(this->get_logger(), "========================================");
    RCLCPP_INFO(this->get_logger(), "摄像头设备: /dev/video%d", camera_device_);
    RCLCPP_INFO(this->get_logger(), "图像分辨率: %dx%d", image_width_, image_height_);
    RCLCPP_INFO(this->get_logger(), "发布频率: %.1f Hz", publish_frequency_);
    RCLCPP_INFO(this->get_logger(), "话题名称: /camera/image_raw");
    RCLCPP_INFO(this->get_logger(), "========================================");
  }

  ~SimpleCameraPublisher() {
    publishing_ = false;
    if (capture_.isOpened()) {
      capture_.release();
    }
    RCLCPP_INFO(this->get_logger(), "摄像头发布者节点已关闭");
  }

private:
  bool init_camera() {
    // 尝试多种方式打开摄像头
    std::vector<std::pair<int, std::string>> open_methods = {
      {cv::CAP_V4L2, "V4L2 API"},
      {cv::CAP_ANY, "Default API"}
    };

    bool camera_opened = false;

    for (const auto& method : open_methods) {
      RCLCPP_INFO(this->get_logger(), "尝试使用 %s 打开摄像头...", method.second.c_str());
      capture_.open(camera_device_, method.first);

      if (capture_.isOpened()) {
        RCLCPP_INFO(this->get_logger(), "✓ 成功使用 %s 打开摄像头", method.second.c_str());
        camera_opened = true;
        break;
      }
    }

    if (!camera_opened) {
      RCLCPP_ERROR(this->get_logger(), "✗ 所有打开方法都失败了");
      return false;
    }

    // 设置摄像头参数
    RCLCPP_INFO(this->get_logger(), "设置摄像头参数...");

    // 设置分辨率
    capture_.set(cv::CAP_PROP_FRAME_WIDTH, image_width_);
    capture_.set(cv::CAP_PROP_FRAME_HEIGHT, image_height_);

    // 设置帧率
    capture_.set(cv::CAP_PROP_FPS, publish_frequency_);

    // 验证设置是否成功
    double actual_width = capture_.get(cv::CAP_PROP_FRAME_WIDTH);
    double actual_height = capture_.get(cv::CAP_PROP_FRAME_HEIGHT);
    double actual_fps = capture_.get(cv::CAP_PROP_FPS);

    RCLCPP_INFO(this->get_logger(), "实际摄像头参数:");
    RCLCPP_INFO(this->get_logger(), "  分辨率: %.0fx%.0f", actual_width, actual_height);
    RCLCPP_INFO(this->get_logger(), "  帧率: %.1f FPS", actual_fps);

    // 测试读取一帧来确保摄像头工作正常
    cv::Mat test_frame;
    int retry_count = 0;
    const int max_retries = 5;

    while (retry_count < max_retries) {
      if (capture_.read(test_frame) && !test_frame.empty()) {
        RCLCPP_INFO(this->get_logger(), "✓ 摄像头测试读取成功");
        RCLCPP_INFO(this->get_logger(), "测试图像尺寸: %dx%d, 通道数: %d",
                    test_frame.cols, test_frame.rows, test_frame.channels());
        return true;
      }
      retry_count++;
      RCLCPP_WARN(this->get_logger(), "摄像头测试读取失败，重试 %d/%d", retry_count, max_retries);
      std::this_thread::sleep_for(std::chrono::milliseconds(500));
    }

    RCLCPP_ERROR(this->get_logger(), "✗ 摄像头测试读取失败，可能摄像头有问题");
    return false;
  }

  void timer_callback() {
    if (!publishing_ || !capture_.isOpened()) {
      return;
    }

    cv::Mat frame;

    // 从摄像头读取帧
    if (!capture_.read(frame) || frame.empty()) {
      static int read_error_count = 0;
      if (read_error_count % 30 == 0) {  // 每秒显示一次错误
        RCLCPP_WARN(this->get_logger(), "无法从摄像头读取帧 (连续失败: %d)", read_error_count);
      }
      read_error_count++;
      return;
    }

    try {
      // 创建ROS2图像消息
      sensor_msgs::msg::Image msg;
      msg.header.stamp = this->now();
      msg.header.frame_id = "camera_frame";
      msg.encoding = "bgr8";
      msg.width = frame.cols;
      msg.height = frame.rows;
      msg.step = frame.cols * frame.elemSize();
      msg.data.resize(frame.total() * frame.elemSize());
      std::memcpy(msg.data.data(), frame.data, msg.data.size());

      // 发布图像消息
      image_publisher_->publish(msg);

      static int frame_count = 0;
      if (frame_count % 30 == 0) {  // 每秒显示一次
        RCLCPP_INFO(this->get_logger(), "发布帧 #%d (%dx%d)",
                    frame_count, msg.width, msg.height);
      }
      frame_count++;

    } catch (const std::exception& e) {
      RCLCPP_ERROR(this->get_logger(), "处理图像时异常: %s", e.what());
    }
  }

  // 成员变量
  cv::VideoCapture capture_;
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr image_publisher_;
  rclcpp::TimerBase::SharedPtr timer_;

  int camera_device_;
  double publish_frequency_;
  int image_width_;
  int image_height_;
  bool publishing_;
};

int main(int argc, char * argv[]) {
  rclcpp::init(argc, argv);

  auto node = std::make_shared<SimpleCameraPublisher>();

  try {
    rclcpp::spin(node);
  } catch (const std::exception& e) {
    RCLCPP_ERROR(node->get_logger(), "异常: %s", e.what());
  }

  rclcpp::shutdown();
  return 0;
}
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/image.hpp"
#include "cv_bridge/cv_bridge.h"
#include <opencv2/opencv.hpp>
#include <memory>
#include <fstream>
#include <filesystem>

class CameraPublisher : public rclcpp::Node {
public:
  CameraPublisher() : Node("camera_publisher"), publishing_(true) {
    // 默认摄像头设备
    camera_device_ = declare_parameter("camera_device", 0);
    // 发布频率 (Hz)
    publish_frequency_ = declare_parameter("publish_frequency", 30.0);
    // 图像宽度
    image_width_ = declare_parameter("image_width", 640);
    // 图像高度
    image_height_ = declare_parameter("image_height", 480);
    // 像素格式
    pixel_format_ = declare_parameter("pixel_format", 0); // 0=自动, 1=MJPG, 2=YUYV

    // 创建图像发布者
    image_publisher_ = this->create_publisher<sensor_msgs::msg::Image>("camera/image_raw", 10);

    // 检查摄像头设备是否存在
    if (!check_camera_device()) {
      RCLCPP_ERROR(this->get_logger(), "摄像头设备 /dev/video%d 不存在", camera_device_);
      return;
    }

    // 初始化摄像头
    if (!init_camera()) {
      RCLCPP_ERROR(this->get_logger(), "无法打开摄像头设备 /dev/video%d", camera_device_);
      RCLCPP_ERROR(this->get_logger(), "请检查:");
      RCLCPP_ERROR(this->get_logger(), "  1. 摄像头是否连接");
      RCLCPP_ERROR(this->get_logger(), "  2. 用户权限: sudo usermod -a -G video $USER");
      RCLCPP_ERROR(this->get_logger(), "  3. 摄像头是否被其他程序占用");
      return;
    }

    // 创建定时器来发布图像
    auto period = std::chrono::duration<double>(1.0 / publish_frequency_);
    timer_ = this->create_wall_timer(
      period, std::bind(&CameraPublisher::timer_callback, this));

    RCLCPP_INFO(this->get_logger(), "========================================");
    RCLCPP_INFO(this->get_logger(), "摄像头发布者节点已启动");
    RCLCPP_INFO(this->get_logger(), "========================================");
    RCLCPP_INFO(this->get_logger(), "摄像头设备: /dev/video%d", camera_device_);
    RCLCPP_INFO(this->get_logger(), "图像分辨率: %dx%d", image_width_, image_height_);
    RCLCPP_INFO(this->get_logger(), "发布频率: %.1f Hz", publish_frequency_);
    RCLCPP_INFO(this->get_logger(), "话题名称: /camera/image_raw");
    RCLCPP_INFO(this->get_logger(), "========================================");
  }

  ~CameraPublisher() {
    publishing_ = false;
    if (capture_.isOpened()) {
      capture_.release();
    }
    RCLCPP_INFO(this->get_logger(), "摄像头发布者节点已关闭");
  }

private:
  bool check_camera_device() {
    std::string device_path = "/dev/video" + std::to_string(camera_device_);
    return std::filesystem::exists(device_path);
  }

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

    // 查询摄像头支持的所有分辨率和格式
    query_camera_capabilities();

    // 设置摄像头参数
    RCLCPP_INFO(this->get_logger(), "设置摄像头参数...");

    // 设置像素格式
    if (pixel_format_ == 1) {
      capture_.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M','J','P','G'));
      RCLCPP_INFO(this->get_logger(), "设置像素格式: MJPEG");
    } else if (pixel_format_ == 2) {
      capture_.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('Y','U','Y','V'));
      RCLCPP_INFO(this->get_logger(), "设置像素格式: YUYV");
    }

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

  void query_camera_capabilities() {
    RCLCPP_INFO(this->get_logger(), "查询摄像头能力...");

    // 获取后端API信息
    std::string backend_name = capture_.getBackendName();
    RCLCPP_INFO(this->get_logger(), "后端API: %s", backend_name.c_str());

    // 检查支持的格式
    int fourcc = static_cast<int>(capture_.get(cv::CAP_PROP_FOURCC));
    if (fourcc != -1) {
      char fourcc_str[5];
      fourcc_str[0] = fourcc & 0XFF;
      fourcc_str[1] = (fourcc >> 8) & 0XFF;
      fourcc_str[2] = (fourcc >> 16) & 0XFF;
      fourcc_str[3] = (fourcc >> 24) & 0XFF;
      fourcc_str[4] = '\0';
      RCLCPP_INFO(this->get_logger(), "当前格式: %s", fourcc_str);
    }

    RCLCPP_INFO(this->get_logger(), "摄像头已成功连接");
  }

  void timer_callback() {
    if (!publishing_ || !capture_.isOpened()) {
      static int error_count = 0;
      if (error_count % 60 == 0) {  // 每2秒显示一次错误
        RCLCPP_ERROR(this->get_logger(), "摄像头未打开或已停止发布");
      }
      error_count++;
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

      // 尝试重新初始化摄像头
      if (read_error_count > 100) {  // 3秒后尝试重新初始化
        RCLCPP_WARN(this->get_logger(), "尝试重新初始化摄像头...");
        if (init_camera()) {
          read_error_count = 0;
          RCLCPP_INFO(this->get_logger(), "摄像头重新初始化成功");
        }
      }
      return;
    }

    // 添加时间戳到图像上（可选）
    // add_timestamp_to_frame(frame);

    try {
      // 创建ROS2图像消息
      sensor_msgs::msg::Image msg;
      msg.header.stamp = this->now();
      msg.header.frame_id = "camera_frame";
      msg.encoding = sensor_msgs::image_encodings::BGR8;
      msg.width = frame.cols;
      msg.height = frame.rows;
      msg.step = frame.cols * frame.elemSize();
      msg.data.resize(frame.total() * frame.elemSize());
      std::memcpy(msg.data.data(), frame.data, msg.data.size());

      // 发布图像消息
      image_publisher_->publish(msg);

      static int frame_count = 0;
      if (frame_count % 30 == 0) {  // 每秒显示一次
        double current_fps = calculate_fps();
        RCLCPP_INFO(this->get_logger(), "发布帧 #%d (%dx%d, FPS: %.1f)",
                    frame_count, msg.width, msg.height, current_fps);
      }
      frame_count++;

    } catch (const cv_bridge::Exception& e) {
      RCLCPP_ERROR(this->get_logger(), "cv_bridge异常: %s", e.what());
    } catch (const std::exception& e) {
      RCLCPP_ERROR(this->get_logger(), "处理图像时异常: %s", e.what());
    }
  }

  double calculate_fps() {
    static auto last_time = this->now();
    static int last_frame_count = 0;

    auto current_time = this->now();
    auto duration = current_time - last_time;
    double elapsed_time = duration.seconds();

    double fps = 0.0;
    if (elapsed_time > 0) {
      fps = 30.0; // 默认估计
    }

    // 每5秒更新一次基准
    static int total_frames = 0;
    total_frames++;

    if (elapsed_time >= 5.0) {
      fps = (total_frames - last_frame_count) / elapsed_time;
      last_time = current_time;
      last_frame_count = total_frames;
    }

    return fps;
  }

  void add_timestamp_to_frame(cv::Mat& frame) {
    // 在图像上添加时间戳
    std::string timestamp = std::to_string(this->now().seconds());
    cv::putText(frame, "ROS2 Camera: " + timestamp,
                cv::Point(10, 30), cv::FONT_HERSHEY_SIMPLEX,
                0.8, cv::Scalar(0, 255, 0), 2);
  }

  // 成员变量
  cv::VideoCapture capture_;
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr image_publisher_;
  rclcpp::TimerBase::SharedPtr timer_;

  std::string frame_encoding_ = sensor_msgs::image_encodings::BGR8;
  int camera_device_;
  double publish_frequency_;
  int image_width_;
  int image_height_;
  int pixel_format_;
  bool publishing_;
};

int main(int argc, char * argv[]) {
  rclcpp::init(argc, argv);

  auto node = std::make_shared<CameraPublisher>();

  try {
    rclcpp::spin(node);
  } catch (const std::exception& e) {
    RCLCPP_ERROR(node->get_logger(), "异常: %s", e.what());
  }

  rclcpp::shutdown();
  return 0;
}
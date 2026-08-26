#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/image.hpp"
#include "cv_bridge/cv_bridge.h"
#include <opencv2/opencv.hpp>
#include <memory>

class CameraSubscriber : public rclcpp::Node {
public:
  CameraSubscriber() : Node("camera_subscriber"), frame_count_(0) {
    // 是否显示图像窗口
    show_image_ = declare_parameter("show_image", true);
    // 窗口名称
    window_name_ = declare_parameter("window_name", "ROS2 Camera Subscriber");

    // 创建图像订阅者
    image_subscription_ = this->create_subscription<sensor_msgs::msg::Image>(
      "camera/image_raw", 10,
      std::bind(&CameraSubscriber::image_callback, this, std::placeholders::_1));

    if (show_image_) {
      cv::namedWindow(window_name_, cv::WINDOW_AUTOSIZE);
      cv::startWindowThread();
    }

    RCLCPP_INFO(this->get_logger(), "摄像头订阅者节点已启动");
    RCLCPP_INFO(this->get_logger(), "订阅话题: /camera/image_raw");
    RCLCPP_INFO(this->get_logger(), "显示图像: %s", show_image_ ? "是" : "否");

    // 创建统计信息定时器
    stats_timer_ = this->create_wall_timer(
      std::chrono::seconds(5),
      std::bind(&CameraSubscriber::print_stats, this));
  }

  ~CameraSubscriber() {
    if (show_image_) {
      cv::destroyWindow(window_name_);
    }
    RCLCPP_INFO(this->get_logger(), "摄像头订阅者节点已关闭");
  }

private:
  void image_callback(const sensor_msgs::msg::Image::SharedPtr msg) {
    try {
      // 将ROS2图像消息转换为OpenCV格式
      cv_bridge::CvImagePtr cv_ptr = cv_bridge::toCvCopy(msg, sensor_msgs::image_encodings::BGR8);

      // 处理图像
      process_image(cv_ptr->image);

      // 显示图像
      if (show_image_) {
        cv::imshow(window_name_, cv_ptr->image);
        cv::waitKey(1);  // 必须调用waitKey来更新窗口
      }

      // 更新统计信息
      frame_count_++;
      if (frame_count_ % 30 == 0) {
        last_fps_ = calculate_fps();
        RCLCPP_INFO(this->get_logger(), "接收帧 #%d (FPS: %.1f)", frame_count_, last_fps_);
      }

    } catch (cv_bridge::Exception& e) {
      RCLCPP_ERROR(this->get_logger(), "cv_bridge异常: %s", e.what());
    } catch (const std::exception& e) {
      RCLCPP_ERROR(this->get_logger(), "处理图像时异常: %s", e.what());
    }
  }

  void process_image(cv::Mat& image) {
    // 这里可以添加图像处理逻辑
    // 例如：边缘检测、人脸检测、物体识别等

    // // 示例：添加处理标记
    // cv::rectangle(image, cv::Point(10, 10), cv::Point(100, 50),
    //               cv::Scalar(255, 0, 0), 2, cv::LINE_AA);

    // 添加FPS信息
    std::string fps_text = "FPS: " + std::to_string(static_cast<int>(last_fps_));
    cv::putText(image, fps_text, cv::Point(15, 35),
                cv::FONT_HERSHEY_SIMPLEX, 0.7, cv::Scalar(255, 255, 255), 2);

    // // 添加接收帧数
    // std::string frame_text = "Frame: " + std::to_string(frame_count_);
    // cv::putText(image, frame_text, cv::Point(15, image.rows - 15),
    //             cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 255, 0), 1);
  }

  double calculate_fps() {
    static auto last_time = this->now();
    static int last_frame_count = 0;

    auto current_time = this->now();
    auto duration = current_time - last_time;
    double elapsed_time = duration.seconds();

    double fps = 0.0;
    if (elapsed_time > 0) {
      fps = (frame_count_ - last_frame_count) / elapsed_time;
    }

    // 每5秒更新一次基准
    if (elapsed_time >= 5.0) {
      last_time = current_time;
      last_frame_count = frame_count_;
    }

    return fps;
  }

  void print_stats() {
    RCLCPP_INFO(this->get_logger(), "=== 统计信息 ===");
    RCLCPP_INFO(this->get_logger(), "总帧数: %d", frame_count_);
    RCLCPP_INFO(this->get_logger(), "当前FPS: %.1f", last_fps_);
    RCLCPP_INFO(this->get_logger(), "订阅者状态: %s",
                image_subscription_->get_publisher_count() > 0 ? "活跃" : "无发布者");
  }

  // 成员变量
  rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr image_subscription_;
  rclcpp::TimerBase::SharedPtr stats_timer_;

  bool show_image_;
  std::string window_name_;
  int frame_count_;
  double last_fps_ = 0.0;
};

int main(int argc, char * argv[]) {
  rclcpp::init(argc, argv);

  auto node = std::make_shared<CameraSubscriber>();

  try {
    rclcpp::spin(node);
  } catch (const std::exception& e) {
    RCLCPP_ERROR(node->get_logger(), "异常: %s", e.what());
  }

  rclcpp::shutdown();
  return 0;
}
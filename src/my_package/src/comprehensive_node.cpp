#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

using namespace std::chrono_literals;

class ComprehensiveNode : public rclcpp::Node {
public:
  ComprehensiveNode() : Node("comprehensive_demo_node"), count_(0) {
    // 1. 话题发布者
    publisher_ = this->create_publisher<std_msgs::msg::String>("demo_topic", 10);
    timer_ = this->create_wall_timer(500ms, std::bind(&ComprehensiveNode::timer_callback, this));

    // 2. 话题订阅者
    subscription_ = this->create_subscription<std_msgs::msg::String>(
      "demo_topic", 10, std::bind(&ComprehensiveNode::topic_callback, this, std::placeholders::_1));

    RCLCPP_INFO(this->get_logger(), "综合节点已启动 - 同时发布和订阅话题！");
  }

private:
  // === 话题相关 ===
  void timer_callback() {
    auto msg = std_msgs::msg::String();
    msg.data = "Hello ROS2! Count: " + std::to_string(count_++);
    RCLCPP_INFO(this->get_logger(), "发布话题消息: '%s'", msg.data.c_str());
    publisher_->publish(msg);
  }

  void topic_callback(const std_msgs::msg::String & msg) const {
    RCLCPP_INFO(this->get_logger(), "收到话题消息: '%s'", msg.data.c_str());
  }

  // === 成员变量 ===
  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr subscription_;
  size_t count_;
};

int main(int argc, char * argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<ComprehensiveNode>());
  rclcpp::shutdown();
  return 0;
}
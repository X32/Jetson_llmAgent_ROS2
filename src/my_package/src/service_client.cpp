#include "rclcpp/rclcpp.hpp"
#include "example_interfaces/srv/add_two_ints.hpp"

// 服务客户端节点
class AddTwoIntsClient : public rclcpp::Node {
public:
  AddTwoIntsClient() : Node("add_two_ints_client") {
    // 创建客户端
    client_ = this->create_client<example_interfaces::srv::AddTwoInts>("add_two_ints");

    // 创建定时器，定期发送请求
    timer_ = this->create_wall_timer(
      std::chrono::milliseconds(2000),
      std::bind(&AddTwoIntsClient::send_request, this));
  }

private:
  void send_request() {
    // 等待服务可用
    if (!client_->wait_for_service(std::chrono::seconds(1))) {
      RCLCPP_WARN(this->get_logger(), "服务不可用，等待中...");
      return;
    }

    // 创建请求
    auto request = std::make_shared<example_interfaces::srv::AddTwoInts::Request>();
    request->a = rand() % 100;
    request->b = rand() % 100;

    RCLCPP_INFO(this->get_logger(), "发送请求: %ld + %ld",
                static_cast<long>(request->a),
                static_cast<long>(request->b));

    // 异步发送请求
    auto future = client_->async_send_request(request);

    // 等待响应
    if (rclcpp::spin_until_future_complete(this->get_node_base_interface(), future) ==
        rclcpp::FutureReturnCode::SUCCESS)
    {
      auto response = future.get();
      RCLCPP_INFO(this->get_logger(), "收到响应: %ld",
                  static_cast<long>(response->sum));
    } else {
      RCLCPP_ERROR(this->get_logger(), "服务调用失败");
    }
  }

  rclcpp::Client<example_interfaces::srv::AddTwoInts>::SharedPtr client_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char * argv[]) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<AddTwoIntsClient>());
  rclcpp::shutdown();
  return 0;
}
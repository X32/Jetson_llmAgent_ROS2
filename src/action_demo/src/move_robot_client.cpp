#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "action_demo/action/move_robot.hpp"
#include <chrono>
#include <functional>

using namespace std::chrono_literals;
using std::placeholders::_1, std::placeholders::_2;

using MoveRobot = action_demo::action::MoveRobot;

/**
 * Action Client：发送移动目标，实时接收feedback，最后拿到result
 * 展示三通道的客户端视角
 */
class MoveRobotClient : public rclcpp::Node {
public:
  explicit MoveRobotClient(const rclcpp::NodeOptions & options = rclcpp::NodeOptions())
  : Node("move_robot_client", options)
  {
    // 创建Action客户端
    client_ = rclcpp_action::create_client<MoveRobot>(this, "move_robot");

    RCLCPP_INFO(this->get_logger(), "MoveRobot Action Client已启动");
  }

  // 发送目标并等待整个流程完成（同步式，便于演示）
  bool send_goal(double target_distance, double target_angle = 0.0, bool test_cancel = false)
  {
    // 等待服务器就绪（最多等5秒）
    if (!client_->wait_for_action_server(5s)) {
      RCLCPP_ERROR(this->get_logger(), "Action Server未上线，退出");
      return false;
    }
    RCLCPP_INFO(this->get_logger(), "已连接到Action Server");

    // ===== 通道1：组装并发送 Goal =====
    auto goal_msg = MoveRobot::Goal();
    goal_msg.target_distance = target_distance;
    goal_msg.target_angle = target_angle;
    RCLCPP_INFO(this->get_logger(), "发送目标: 移动 %.2f 米, 方向 %.0f 度",
                target_distance, target_angle);

    // 设置目标响应回调和结果回调
    auto send_goal_options = rclcpp_action::Client<MoveRobot>::SendGoalOptions();

    // 目标被服务器接受/拒绝后的回调
    send_goal_options.goal_response_callback =
      [this](rclcpp_action::ClientGoalHandle<MoveRobot>::SharedPtr goal_handle) {
        if (!goal_handle) {
          RCLCPP_ERROR(this->get_logger(), ">> 目标被服务器 [拒绝]");
        } else {
          RCLCPP_INFO(this->get_logger(), ">> 目标被服务器 [接受]，goal_handle已获得");
        }
      };

    // ===== 通道2：Feedback 回调（执行中持续触发） =====
    send_goal_options.feedback_callback =
      [this](typename rclcpp_action::ClientGoalHandle<MoveRobot>::SharedPtr,
             const std::shared_ptr<const MoveRobot::Feedback> feedback) {
        RCLCPP_INFO(this->get_logger(),
                    ">> [Feedback] 进度: %.0f%% | 位置(%.2f, %.2f) | 剩余: %.2f米",
                    feedback->progress * 100.0,
                    feedback->pose_x,
                    feedback->pose_y,
                    feedback->remaining_distance);
      };

    // ===== 通道3：Result 回调（任务结束时触发一次） =====
    send_goal_options.result_callback =
      [this](const rclcpp_action::ClientGoalHandle<MoveRobot>::WrappedResult & result) {
        switch (result.code) {
          case rclcpp_action::ResultCode::SUCCEEDED:
            RCLCPP_INFO(this->get_logger(),
                        ">> [Result] 成功! 实际移动: %.2f米 | 用时: %.2f秒",
                        result.result->actual_distance, result.result->elapsed_time);
            break;
          case rclcpp_action::ResultCode::CANCELED:
            RCLCPP_WARN(this->get_logger(),
                        ">> [Result] 被取消! 实际移动: %.2f米", result.result->actual_distance);
            break;
          case rclcpp_action::ResultCode::ABORTED:
            RCLCPP_ERROR(this->get_logger(), ">> [Result] 异常中止");
            break;
          default:
            RCLCPP_ERROR(this->get_logger(), ">> [Result] 未知结果码");
        }
        result_received_ = true;
      };

    // 异步发送目标
    auto goal_handle_future = client_->async_send_goal(goal_msg, send_goal_options);

    // 演示取消功能：3秒后取消任务
    if (test_cancel) {
      // 简单处理：睡3秒后发取消（实际项目用回调+状态机）
      std::thread([this, goal_handle_future]() {
                  std::this_thread::sleep_for(3s);
                  auto goal_handle = goal_handle_future.get();
                  if (goal_handle) {
                    RCLCPP_WARN(this->get_logger(), "客户端主动请求 [取消] 任务...");
                    client_->async_cancel_goal(goal_handle);
                  }
                }).detach();
    }

    // 等待结果（spin由外部负责）
    return true;
  }

  bool is_done() const { return result_received_; }

private:
  rclcpp_action::Client<MoveRobot>::SharedPtr client_;
  std::atomic<bool> result_received_{false};
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<MoveRobotClient>();

  // 用法:
  //   move_robot_client <距离> [角度]    默认: 2.5米 0度
  //   move_robot_client cancel           演示中途取消
  double target = 2.5;
  double angle = 0.0;
  bool test_cancel = false;
  if (argc >= 2) {
    std::string arg = argv[1];
    if (arg == "cancel") {
      test_cancel = true;
      target = 10.0;
    } else {
      target = std::atof(argv[1]);
      if (argc >= 3) angle = std::atof(argv[2]);
    }
  }

  // 延迟发送，给服务器一点上线时间（launch中两者同时启动）
  std::thread sender([node, target, angle, test_cancel]() {
    std::this_thread::sleep_for(1s);
    node->send_goal(target, angle, test_cancel);
  });
  sender.detach();

  // spin处理各类回调（goal响应/feedback/result）
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}


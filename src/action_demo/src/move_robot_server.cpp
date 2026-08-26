#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "action_demo/action/move_robot.hpp"
#include <opencv2/opencv.hpp>

using namespace std::chrono_literals;
using std::placeholders::_1, std::placeholders::_2;

// 类型别名，简化代码
using MoveRobot = action_demo::action::MoveRobot;
using GoalHandleMoveRobot = rclcpp_action::ServerGoalHandle<MoveRobot>;

/**
 * Action Server：模拟机器人移动控制 + 乌龟可视化
 * 三通道分工：
 *   Goal     —— 接收目标（handle_goal）
 *   Feedback —— 执行中上报进度（execute循环里publish feedback）
 *   Result   —— 完成后返回结果（execute结束前publish result）
 * 可视化：OpenCV窗口显示乌龟图标沿方向移动，蓝色轨迹线
 */
class MoveRobotServer : public rclcpp::Node {
public:
  explicit MoveRobotServer(const rclcpp::NodeOptions & options = rclcpp::NodeOptions())
  : Node("move_robot_server", options)
  {
    // 创建Action服务器
    action_server_ = rclcpp_action::create_server<MoveRobot>(
      this,
      "move_robot",
      std::bind(&MoveRobotServer::handle_goal, this, _1, _2),
      std::bind(&MoveRobotServer::handle_cancel, this, _1),
      std::bind(&MoveRobotServer::handle_accepted, this, _1));

    // ===== 可视化状态 =====
    // 世界坐标（米），初始在画布中心
    pose_x_ = 0.0;
    pose_y_ = 0.0;
    heading_ = 0.0;   // 当前朝向（度）

    // 画布：600x600像素，比例尺100像素/米
    canvas_ = cv::Mat(600, 600, CV_8UC3, cv::Scalar(250, 248, 240));
    draw_grid();

    // 禁用可视化窗口
    // cv::namedWindow("MoveRobot Turtle", cv::WINDOW_AUTOSIZE);
    // render_turtle();  // 画初始位置

    RCLCPP_INFO(this->get_logger(), "MoveRobot Action Server已启动（轨迹可视化）");
    RCLCPP_INFO(this->get_logger(), "Action名称: move_robot | 画布比例: 100px/米");
  }

private:
  rclcpp_action::Server<MoveRobot>::SharedPtr action_server_;

  // 可视化状态
  double pose_x_, pose_y_;    // 世界坐标（米）
  double heading_;            // 朝向（度）
  cv::Mat canvas_;            // 画布
  std::mutex canvas_mutex_;   // 画布锁（execute在线程里跑）
  const double SCALE = 100.0; // 像素/米
  const cv::Point2d ORIGIN = cv::Point2d(300, 300);  // 世界原点在画布中心

  // 世界坐标(米) -> 画布像素坐标（注意图像y向下）
  cv::Point2d world_to_pixel(double wx, double wy)
  {
    return cv::Point2d(ORIGIN.x + wx * SCALE, ORIGIN.y - wy * SCALE);
  }

  void draw_grid()
  {
    // 每1米画一条浅灰网格线
    for (int m = -3; m <= 3; ++m) {
      auto v = world_to_pixel(m, 0);
      auto h = world_to_pixel(0, m);
      cv::line(canvas_, cv::Point(v.x, 0), cv::Point(v.x, 599),
               cv::Scalar(225, 222, 214), 1);
      cv::line(canvas_, cv::Point(0, h.y), cv::Point(599, h.y),
               cv::Scalar(225, 222, 214), 1);
    }
  }

  // 在画布上画简化乌龟（单个圆圈+箭头，大幅提高性能）
  void draw_turtle(cv::Mat & img, cv::Point2d center, double angle_deg, int size)
  {
    double rad = angle_deg * CV_PI / 180.0;
    // 方向向量：数学角度（0=+x, 90=+y），图像y翻转
    cv::Point2d dir(std::cos(rad), -std::sin(rad));

    // 简化乌龟：绿色圆圈表示身体
    cv::circle(img, center, size, cv::Scalar(80, 160, 60), -1, cv::LINE_AA);
    cv::circle(img, center, size, cv::Scalar(40, 100, 30), 2, cv::LINE_AA);

    // 箭头表示朝向（在圆圈前面）
    cv::Point2d arrow_tip = center + dir * (size + 6);
    cv::Point2d arrow_left = arrow_tip - dir * 4 + cv::Point2d(-dir.y, dir.x) * 3;
    cv::Point2d arrow_right = arrow_tip - dir * 4 - cv::Point2d(-dir.y, dir.x) * 3;

    // 画箭头（三角形）
    std::vector<cv::Point> arrow_pts = {arrow_tip, arrow_left, arrow_right};
    cv::fillConvexPoly(img, arrow_pts, cv::Scalar(60, 140, 50), cv::LINE_AA);
  }

  // 渲染当前帧：轨迹已在canvas上，叠加乌龟并显示
  void render_turtle()
  {
    std::lock_guard<std::mutex> lock(canvas_mutex_);
    cv::Mat frame = canvas_.clone();

    // 起点标记
    cv::circle(frame, world_to_pixel(0, 0), 4, cv::Scalar(0, 0, 255), -1);
    cv::putText(frame, "start", world_to_pixel(0, 0) + cv::Point2d(6, -6),
                cv::FONT_HERSHEY_SIMPLEX, 0.4, cv::Scalar(0, 0, 200), 1);

    // 乌龟
    draw_turtle(frame, world_to_pixel(pose_x_, pose_y_), heading_, 14);

    // 状态文字
    std::string info = cv::format("pose(%.2f, %.2f)m  heading:%.0fdeg", pose_x_, pose_y_, heading_);
    cv::putText(frame, info, cv::Point(10, 20), cv::FONT_HERSHEY_SIMPLEX,
                0.5, cv::Scalar(60, 60, 60), 1);

    cv::imshow("MoveRobot Turtle", frame);
    cv::waitKey(1);
  }

  // ========== 通道1：Goal（目标请求） ==========
  rclcpp_action::GoalResponse handle_goal(const rclcpp_action::GoalUUID & /*uuid*/,
                                          std::shared_ptr<const MoveRobot::Goal> goal)
  {
    RCLCPP_INFO(this->get_logger(), "收到目标请求: 移动 %.2f 米, 方向 %.0f 度",
                goal->target_distance, goal->target_angle);

    if (std::abs(goal->target_distance) < 0.01 || std::abs(goal->target_distance) > 10.0) {
      RCLCPP_WARN(this->get_logger(), "目标被拒绝: 距离必须在 0.01~10 米之间");
      return rclcpp_action::GoalResponse::REJECT;
    }

    RCLCPP_INFO(this->get_logger(), "目标已接受，开始执行");
    return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
  }

  rclcpp_action::CancelResponse handle_cancel(const std::shared_ptr<GoalHandleMoveRobot> goal_handle)
  {
    RCLCPP_INFO(this->get_logger(), "收到取消请求: 移动 %.2f 米的任务被取消",
                goal_handle->get_goal()->target_distance);
    return rclcpp_action::CancelResponse::ACCEPT;
  }

  void handle_accepted(const std::shared_ptr<GoalHandleMoveRobot> goal_handle)
  {
    std::thread{std::bind(&MoveRobotServer::execute, this, _1), goal_handle}.detach();
  }

  // ========== 通道2+3：Feedback（进度反馈）+ Result（最终结果） ==========
  void execute(const std::shared_ptr<GoalHandleMoveRobot> goal_handle)
  {
    RCLCPP_INFO(this->get_logger(), "====== 开始执行移动任务 ======");

    const auto goal = goal_handle->get_goal();
    auto feedback = std::make_shared<MoveRobot::Feedback>();
    auto result = std::make_shared<MoveRobot::Result>();

    // 模拟参数：速度1米/秒，每100ms更新一次
    const double speed = 1.0;   // m/s
    const double dt = 0.1;      // 100ms
    rclcpp::Time start_time = this->now();

    // 更新朝向并锁定
    heading_ = goal->target_angle;
    const double rad = heading_ * CV_PI / 180.0;

    double moved = 0.0;  // 本次任务已移动的距离
    auto prev_px = world_to_pixel(pose_x_, pose_y_);  // 轨迹起点（像素）
    int loop_count = 0;  // 循环计数器，用于降低渲染频率

    while (moved < std::abs(goal->target_distance)) {
      if (goal_handle->is_canceling()) {
        result->actual_distance = moved;
        result->elapsed_time = (this->now() - start_time).seconds();
        result->success = false;
        goal_handle->canceled(result);
        // 禁用取消时的可视化显示
        // render_turtle();
        RCLCPP_WARN(this->get_logger(), "任务已取消: 本次实际移动 %.2f 米（目标 %.2f 米）",
                    moved, goal->target_distance);
        return;
      }

      auto step_start = std::chrono::high_resolution_clock::now();

      // 推进距离
      double step = std::min(speed * dt, std::abs(goal->target_distance) - moved);
      moved += step;
      pose_x_ += std::cos(rad) * step * (goal->target_distance > 0 ? 1.0 : -1.0);
      pose_y_ += std::sin(rad) * step * (goal->target_distance > 0 ? 1.0 : -1.0);

      auto step_calc_time = std::chrono::high_resolution_clock::now();
      double calc_ms = std::chrono::duration<double, std::milli>(step_calc_time - step_start).count();

      // ===== 画轨迹线（在canvas上留下永久轨迹） =====
      auto draw_start = std::chrono::high_resolution_clock::now();
      {
        std::lock_guard<std::mutex> lock(canvas_mutex_);
        auto cur_px = world_to_pixel(pose_x_, pose_y_);
        cv::line(canvas_, prev_px, cur_px, cv::Scalar(220, 120, 40), 2, cv::LINE_AA);
        prev_px = cur_px;
      }
      auto draw_time = std::chrono::high_resolution_clock::now();
      double draw_ms = std::chrono::duration<double, std::milli>(draw_time - draw_start).count();

      // ===== 发布 Feedback =====
      auto pub_start = std::chrono::high_resolution_clock::now();
      feedback->progress = moved / std::abs(goal->target_distance);
      feedback->current_distance = moved;
      feedback->remaining_distance = std::abs(goal->target_distance) - moved;
      feedback->pose_x = pose_x_;
      feedback->pose_y = pose_y_;
      goal_handle->publish_feedback(feedback);
      auto pub_time = std::chrono::high_resolution_clock::now();
      double pub_ms = std::chrono::duration<double, std::milli>(pub_time - pub_start).count();

      // ===== 暂时禁用实时渲染（OpenCV显示环境问题） =====
      // TODO: 等任务完成后再显示最终位置
      // if (loop_count % 5 == 0) {
      //   render_turtle();
      // }
      double render_ms = 0.0;  // 暂时设为0，避免性能日志错误

      // ===== 日志输出（每20次输出一次性能统计） =====
     // if (loop_count % 20 == 0) {
        RCLCPP_INFO(this->get_logger(),
                    "[PERF] 循环 #%d | 计算=%.2fms | 画线=%.2fms | 发布=%.2fms | 渲染=%.2fms | 总计=%.2fms",
                    loop_count, calc_ms, draw_ms, pub_ms, render_ms,
                    calc_ms + draw_ms + pub_ms + render_ms);
      //}

      loop_count++;
      std::this_thread::sleep_for(100ms);
    }

    // ===== 发布 Result =====
    result->actual_distance = moved;
    result->elapsed_time = (this->now() - start_time).seconds();
    result->success = true;
    goal_handle->succeed(result);

    // 禁用完成时的可视化显示
    // render_turtle();
    // cv::waitKey(3000);

    RCLCPP_INFO(this->get_logger(), "====== 任务完成 ======");
    RCLCPP_INFO(this->get_logger(), "结果: 本次移动 %.2f米 | 用时 %.2f秒 | 终点(%.2f, %.2f) | 成功=%s",
                result->actual_distance, result->elapsed_time,
                pose_x_, pose_y_, result->success ? "true" : "false");
  }
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<MoveRobotServer>();

  // 简化为标准ROS2 spin（不再需要OpenCV事件循环）
  rclcpp::spin(node);

  rclcpp::shutdown();
  // cv::destroyAllWindows();  // 不再需要OpenCV清理
  return 0;
}

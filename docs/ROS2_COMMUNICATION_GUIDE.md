# ROS2 通信机制完整指南

## 1. 核心概念关系图

```
┌─────────────────────────────────────────────────────┐
│                    ROS2 节点系统                      │
└─────────────────────────────────────────────────────┘
           │                  │                 │
           ▼                  ▼                 ▼
    ┌────────────┐    ┌────────────┐    ┌────────────┐
    │   话题      │    │   服务      │    │   动作      │
    │ (Topic)    │    │ (Service)  │    │ (Action)   │
    └────────────┘    └────────────┘    └────────────┘
    • 单向异步         • 双向同步         • 三向异步
    • 发布/订阅        • 请求/响应        • 目标/反馈/结果
    • 数据流           • 短任务           • 长任务
```

## 2. 节点 (Node)

**定义：** ROS2的基本执行单元，每个节点都是一个独立的进程。

**节点能力：**
- ✅ 可以发布和订阅话题
- ✅ 可以提供和调用服务
- ✅ 可以执行和调用动作
- ✅ 可以使用参数服务器

**创建节点的方式：**

```cpp
// 方式1：直接创建简单节点
auto node = rclcpp::Node::make_shared("my_node");

// 方式2：继承Node类（推荐）
class MyNode : public rclcpp::Node {
public:
  MyNode() : Node("my_node") {
    // 初始化节点功能
  }
};
```

## 3. 话题 (Topic) - 异步通信

**特点：**
- 🔄 单向通信（发布者 → 订阅者）
- 📤 异步、解耦
- 📡 多对多关系
- 🎛️ 适合持续数据流

**使用场景：**
- 相机图像流
- 传感器数据（IMU、激光雷达）
- 机器人状态信息
- 控制命令

**代码示例：**

```cpp
// 发布者
class PublisherNode : public rclcpp::Node {
public:
  PublisherNode() : Node("publisher_node") {
    // 创建发布者
    publisher_ = this->create_publisher<std_msgs::msg::String>("my_topic", 10);
    
    // 创建定时器定期发布
    timer_ = this->create_wall_timer(
      500ms, std::bind(&PublisherNode::publish_callback, this));
  }

private:
  void publish_callback() {
    auto msg = std_msgs::msg::String();
    msg.data = "Hello ROS2!";
    publisher_->publish(msg);
  }

  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
};

// 订阅者
class SubscriberNode : public rclcpp::Node {
public:
  SubscriberNode() : Node("subscriber_node") {
    // 创建订阅者
    subscription_ = this->create_subscription<std_msgs::msg::String>(
      "my_topic", 10,
      std::bind(&SubscriberNode::subscribe_callback, this, std::placeholders::_1));
  }

private:
  void subscribe_callback(const std_msgs::msg::String & msg) const {
    RCLCPP_INFO(this->get_logger(), "收到: '%s'", msg.data.c_str());
  }

  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr subscription_;
};
```

## 4. 服务 (Service) - 同步通信

**特点：**
- 🔄 双向通信（客户端 ↔ 服务端）
- 📤 同步、阻塞
- 📡 一对多关系（一个服务端，多个客户端）
- 🎛️ 适合简单请求-响应场景

**使用场景：**
- 计算服务（加法、乘法）
- 配置查询
- 状态查询
- 短时间任务

**代码示例：**

```cpp
// 服务端
class ServiceServer : public rclcpp::Node {
public:
  ServiceServer() : Node("service_server") {
    // 创建服务
    service_ = this->create_service<example_interfaces::srv::AddTwoInts>(
      "add_two_ints",
      std::bind(&ServiceServer::handle_service, this,
                std::placeholders::_1, std::placeholders::_2));
  }

private:
  void handle_service(
    const std::shared_ptr<example_interfaces::srv::AddTwoInts::Request> request,
    std::shared_ptr<example_interfaces::srv::AddTwoInts::Response> response)
  {
    response->sum = request->a + request->b;
    RCLCPP_INFO(this->get_logger(), "%d + %d = %d",
                request->a, request->b, response->sum);
  }

  rclcpp::Service<example_interfaces::srv::AddTwoInts>::SharedPtr service_;
};

// 客户端
class ServiceClient : public rclcpp::Node {
public:
  ServiceClient() : Node("service_client") {
    // 创建客户端
    client_ = this->create_client<example_interfaces::srv::AddTwoInts>("add_two_ints");
    
    // 定时器定期调用服务
    timer_ = this->create_wall_timer(
      2000ms, std::bind(&ServiceClient::call_service, this));
  }

private:
  void call_service() {
    // 等待服务可用
    if (!client_->wait_for_service(1s)) {
      RCLCPP_WARN(this->get_logger(), "服务不可用");
      return;
    }

    // 创建请求
    auto request = std::make_shared<example_interfaces::srv::AddTwoInts::Request>();
    request->a = 10;
    request->b = 20;

    // 异步调用服务
    auto future = client_->async_send_request(request);
    
    // 等待响应
    if (rclcpp::spin_until_future_complete(this->get_node_base_interface(), future) ==
        rclcpp::FutureReturnCode::SUCCESS)
    {
      auto response = future.get();
      RCLCPP_INFO(this->get_logger(), "结果: %d", response->sum);
    }
  }

  rclcpp::Client<example_interfaces::srv::AddTwoInts>::SharedPtr client_;
  rclcpp::TimerBase::SharedPtr timer_;
};
```

## 5. 动作 (Action) - 长任务通信

**特点：**
- 🔄 三向通信（客户端 ↔ 动作服务器）
- 📤 支持取消、进度反馈、状态查询
- 📡 一对多关系
- 🎛️ 适合长时间运行的任务

**使用场景：**
- 导航路径规划
- 机械臂运动控制
- SLAM建图
- 长时间计算任务

**动作通信流程：**

```
客户端                    动作服务器
  │                           │
  ├───── 目标 (Goal) ─────────→│
  │                           │
  │←───── 反馈 (Feedback) ─────┤
  │                           │
  │←───── 结果 (Result) ───────┤
  │                           │
  ├───── 取消 (Cancel) ───────→│  (可选)
```

**代码示例：**

```cpp
// 动作服务器
class ActionServer : public rclcpp::Node {
public:
  ActionServer() : Node("action_server") {
    action_server_ = rclcpp_action::create_server<Fibonacci>(
      this, "fibonacci",
      std::bind(&ActionServer::handle_goal, this, std::placeholders::_1),
      std::bind(&ActionServer::handle_cancel, this, std::placeholders::_1),
      std::bind(&ActionServer::handle_accepted, this, std::placeholders::_1));
  }

private:
  rclcpp_action::Server<Fibonacci>::SharedPtr action_server_;

  rclcpp_action::GoalResponse handle_goal(
    const rclcpp_action::GoalUUID & uuid,
    std::shared_ptr<const Fibonacci::Goal> goal)
  {
    return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
  }

  rclcpp_action::CancelResponse handle_cancel(
    const std::shared_ptr<rclcpp_action::ServerGoalHandle<Fibonacci>> goal_handle)
  {
    return rclcpp_action::CancelResponse::ACCEPT;
  }

  void handle_accepted(const std::shared_ptr<rclcpp_action::ServerGoalHandle<Fibonacci>> goal_handle) {
    // 在新线程中执行目标
    std::thread{std::bind(&ActionServer::execute, this, std::placeholders::_1), goal_handle}.detach();
  }

  void execute(const std::shared_ptr<rclcpp_action::ServerGoalHandle<Fibonacci>> goal_handle) {
    // 执行长任务并发送反馈
    auto feedback = std::make_shared<Fibonacci::Feedback>();
    auto result = std::make_shared<Fibonacci::Result>();
    
    // 执行任务逻辑...
    for (int i = 0; i < goal_handle->get_goal()->order; ++i) {
      feedback->sequence.push_back(i);
      goal_handle->publish_feedback(feedback);
    }
    
    goal_handle->succeed(result);
  }
};

// 动作客户端
class ActionClient : public rclcpp::Node {
public:
  ActionClient() : Node("action_client") {
    action_client_ = rclcpp_action::create_client<Fibonacci>(this, "fibonacci");
  }

  void send_goal(int order) {
    if (!action_client_->wait_for_action_server(1s)) {
      RCLCPP_ERROR(this->get_logger(), "动作服务器不可用");
      return;
    }

    auto goal_msg = Fibonacci::Goal();
    goal_msg.order = order;

    auto goal_options = rclcpp_action::Client<Fibonacci>::SendGoalOptions();
    goal_options.feedback_callback = 
      std::bind(&ActionClient::feedback_callback, this, std::placeholders::_1, std::placeholders::_2);
    
    auto future_goal_handle = action_client_->async_send_goal(goal_msg, goal_options);
  }

private:
  void feedback_callback(
    rclcpp_action::ClientGoalHandle<Fibonacci>::SharedPtr,
    const std::shared_ptr<const Fibonacci::Feedback> feedback)
  {
    RCLCPP_INFO(this->get_logger(), "收到反馈");
  }

  rclcpp_action::Client<Fibonacci>::SharedPtr action_client_;
};
```

## 6. 对比总结表

| 特性 | 话题 (Topic) | 服务 (Service) | 动作 (Action) |
|------|-------------|---------------|---------------|
| **通信模式** | 单向发布/订阅 | 双向请求/响应 | 三向(目标/反馈/结果) |
| **同步性** | 异步 | 同步 | 异步 |
| **通信关系** | 多对多 | 一对多 | 一对多 |
| **可取消** | ❌ | ❌ | ✅ |
| **进度反馈** | ❌ | ❌ | ✅ |
| **阻塞客户端** | ❌ | ✅ | ❌ |
| **适用场景** | 持续数据流 | 简单查询响应 | 长时间任务 |
| **典型例子** | 相机图像、IMU | 计算服务、配置 | 导航、路径规划 |
| **消息类型** | Msg | Srv | Action |

## 7. 实战示例运行

**编译所有示例：**

```bash
cd /mnt/apfs/workplace/ROS2
source /opt/ros/humble/setup.bash
colcon build --packages-select my_package
source install/setup.bash
```

**运行话题示例：**
```bash
# 终端1：发布者
ros2 run my_package publisher_node

# 终端2：订阅者  
ros2 run my_package subscriber_node

# 监控话题
ros2 topic list
ros2 topic echo /topic
```

**运行服务示例：**
```bash
# 终端1：服务端
ros2 run my_package service_server

# 终端2：客户端
ros2 run my_package service_client

# 调用服务命令行
ros2 service call /add_two_ints example_interfaces/srv/AddTwoInts "{a: 5, b: 3}"
```

**运行综合示例：**
```bash
# 单个节点同时使用话题和服务
ros2 run my_package comprehensive_node
```

## 8. 常用命令

**话题相关：**
```bash
ros2 topic list                          # 列出所有话题
ros2 topic info <topic_name>             # 查看话题信息
ros2 topic echo <topic_name>             # 监听话题消息
ros2 topic hz <topic_name>               # 查看话题发布频率
```

**服务相关：**
```bash
ros2 service list                        # 列出所有服务
ros2 service type <service_name>         # 查看服务类型
ros2 service call <service_name> <type> <args>  # 调用服务
```

**节点相关：**
```bash
ros2 node list                           # 列出所有节点
ros2 node info <node_name>              # 查看节点详细信息
```

## 9. 选择建议

**使用话题，如果：**
- 📡 需要持续的数据流
- 🔄 发送者和接收者解耦
- 📤 高频率、小数据量传输

**使用服务，如果：**
- 🔍 需要同步的请求-响应
- ⏱️ 短时间的计算任务
- 🎯 需要立即返回结果

**使用动作，如果：**
- ⏰ 长时间运行的任务
- 📊 需要进度反馈
- ❌ 需要取消功能
- 🔧 复杂的多步骤任务

通过这些示例，你可以看到ROS2节点确实可以**订阅话题**（如你的subscriber_node.cpp所示），并且可以同时使用多种通信机制（如comprehensive_node.cpp所示）！
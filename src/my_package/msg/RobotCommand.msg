# llm_agent → robot_controller 的指令契约（阶段三.md Day7）
string action          # 动作原语: move_forward / turn_left / turn_right / stop / query_sensor
float32 distance       # 前进距离（米），仅 move_forward 有效
float32 angle          # 转弯角度（度），仅 turn_left / turn_right 有效
string sensor_type     # lidar / camera，仅 query_sensor 有效（Day9 实装）

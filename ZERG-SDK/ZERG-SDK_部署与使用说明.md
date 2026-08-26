# Z-ERG-20C SDK 与 ROS 2 驱动部署和使用说明

本文档说明如何在 Ubuntu 22.04 和 ROS 2 Humble 环境中部署、启动和使用
Z-ERG-20C 旋转电爪。

设备协议依据项目根目录中的 `Z-ERG-20C.pdf`，默认通信参数为：

```text
协议：Modbus RTU
串口：RS485
波特率：115200
数据位：8
停止位：1
校验位：无
设备 ID：1
浮点字节序：大端
```

## 1. 项目结构

```text
ZERG-SDK/
├── zerg_sdk/            纯 Python 通信 SDK
├── zerg_interfaces/     ROS 2 Action 接口
├── zerg_ros2_driver/    ROS 2 驱动节点
├── Z-ERG-20C.pdf        厂商产品和通信协议手册
└── ZERG-SDK_部署与使用说明.md
```

三个 ROS 2 Action 分别为：

| Action 名称 | Action 类型 | 功能 |
| --- | --- | --- |
| `/zerg_driver/open` | `zerg_interfaces/action/OpenGripper` | 完全张开到 20 mm |
| `/zerg_driver/close` | `zerg_interfaces/action/CloseGripper` | 完全闭合到 0 mm |
| `/zerg_driver/rotate` | `zerg_interfaces/action/RotateMotor` | 有符号相对旋转 |

## 2. 硬件连接

### 2.1 供电和 RS485

按设备手册连接：

```text
红色线：24V+
黑色线：0V/GND
黄色线：RS485 A/T+
黄白线：RS485 B/T-
```

设备内部 RS485 和 24 V 电源没有隔离。USB-RS485 转接器也没有隔离时，
应连接夹爪 0V/GND 与转接器 GND。

通电前必须检查：

- 24 V 正负极没有接反。
- RS485 A/B 没有接反。
- 夹指行程内没有障碍物。
- 旋转时线缆不会缠绕或拉扯。

### 2.2 检查 CH340 转接器

```bash
lsusb
```

CH340 通常显示为：

```text
ID 1a86:7523 QinHeng Electronics CH340 serial converter
```

检查串口节点：

```bash
ls -l /dev/ttyUSB0
```

如果插入设备后短暂出现 `ttyUSB0`，随后立即消失，并且 `dmesg` 中出现：

```text
usbfs: interface 0 claimed by ch341 while 'brltty' sets config #1
```

说明 BRLTTY 抢占了 CH340。如果电脑不使用盲文显示器，可以卸载：

```bash
sudo apt remove brltty
```

然后重新拔插 CH340。

### 2.3 永久串口权限

将当前用户加入 `dialout` 组：

```bash
sudo usermod -aG dialout "$USER"
```

执行后必须注销并重新登录，或者重启电脑。验证：

```bash
groups
```

输出中应包含 `dialout`。

仅用于临时测试的授权方式为：

```bash
sudo chmod 666 /dev/ttyUSB0
```

该权限会在 USB 拔插或系统重启后失效，不应作为长期部署方案。

## 3. 环境依赖

推荐环境：

```text
Ubuntu 22.04
ROS 2 Humble
Python 3.10
pyserial 3.5 或更高版本
```

加载 ROS 2 环境：

```bash
source /opt/ros/humble/setup.bash
```

确认工具存在：

```bash
ros2 --help
colcon --help
python3 --version
```

## 4. 首次部署

以下命令均在项目根目录执行：

```bash
cd /home/sxkc/ZERG-SDK
```

### 4.1 安装纯 Python SDK

```bash
python3 -m pip install --user -e ./zerg_sdk
```

参数含义：

- `--user`：安装到当前用户的 `~/.local`，不修改系统 Python。
- `-e`：可编辑安装，源码修改后不需要重新安装。
- `./zerg_sdk`：SDK 项目目录。

检查安装结果：

```bash
python3 -m pip show zerg-sdk
```

为了避免项目根目录的同名目录干扰验证，应从其他目录测试导入：

```bash
cd /tmp
python3 -c "import zerg_sdk; print(zerg_sdk.__file__)"
```

正常输出类似：

```text
/home/sxkc/ZERG-SDK/zerg_sdk/zerg_sdk/__init__.py
```

如果输出 `None`，说明导入的是项目外层形成的命名空间，而不是已安装的 SDK。

### 4.2 安装 ROS 依赖

```bash
cd /home/sxkc/ZERG-SDK
source /opt/ros/humble/setup.bash

rosdep install \
  --from-paths zerg_interfaces zerg_ros2_driver \
  --ignore-src -r -y
```

### 4.3 编译 ROS 2 包

```bash
colcon build --symlink-install \
  --packages-select zerg_interfaces zerg_ros2_driver
```

加载本工作区：

```bash
source install/setup.bash
```

验证接口：

```bash
ros2 interface list | grep zerg_interfaces/action
```

预期输出：

```text
zerg_interfaces/action/OpenGripper
zerg_interfaces/action/CloseGripper
zerg_interfaces/action/RotateMotor
```

## 5. 驱动配置

默认配置文件：

```text
zerg_ros2_driver/config/zerg_driver.yaml
```

主要参数：

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `port` | `/dev/ttyUSB0` | 串口设备 |
| `baudrate` | `115200` | Modbus RTU 波特率 |
| `slave_id` | `1` | 夹爪设备 ID |
| `serial_timeout_s` | `0.2` | 单次串口超时 |
| `byte_order` | `big` | 32 位数据字节序 |
| `poll_rate_hz` | `20.0` | 状态轮询频率 |
| `reconnect_interval_s` | `2.0` | 断线重连间隔 |
| `motion_timeout_s` | `15.0` | Action 最大等待时间 |
| `feedback_rate_hz` | `10.0` | Action 反馈频率 |
| `grip_tolerance_mm` | `0.2` | 夹持位置到位容差 |
| `rotation_tolerance_deg` | `1.0` | 旋转角度到位容差 |
| `default_grip_speed_mm_s` | `50.0` | 默认夹持速度 |
| `default_grip_current_a` | `0.3` | 默认夹持电流上限 |
| `default_rotation_speed_deg_s` | `360.0` | 默认旋转速度 |
| `default_rotation_current_a` | `0.8` | 默认旋转电流上限 |

修改 YAML 后重新启动驱动即可生效，不需要重新编译。

需要临时覆盖参数时，可以不使用 launch 文件，直接运行节点：

```bash
ros2 run zerg_ros2_driver zerg_driver --ros-args \
  -p port:=/dev/ttyUSB1 \
  -p slave_id:=1 \
  -p baudrate:=115200
```

当前 launch 文件直接加载 YAML，没有声明 launch 参数。使用 `ros2 launch` 时，应修改
`zerg_ros2_driver/config/zerg_driver.yaml`。由于工作区使用 `--symlink-install`，修改
YAML 后通常无需重新编译，重新启动节点即可。

## 6. 启动驱动

打开终端 1：

```bash
cd /home/sxkc/ZERG-SDK
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 launch zerg_ros2_driver zerg_driver.launch.py
```

连接成功时会显示：

```text
Z-ERG-20C driver started; waiting for serial device
connected to Z-ERG-20C
```

保持终端 1 运行。ROS 驱动运行期间，不要启动其他直接访问
`/dev/ttyUSB0` 的脚本，否则会发生串口争用。

## 7. 检查 ROS 接口

打开终端 2，每个新终端都必须加载环境：

```bash
source /opt/ros/humble/setup.bash
source /home/sxkc/ZERG-SDK/install/setup.bash
```

查看三个 Action：

```bash
ros2 action list -t
```

预期包含：

```text
/zerg_driver/open [zerg_interfaces/action/OpenGripper]
/zerg_driver/close [zerg_interfaces/action/CloseGripper]
/zerg_driver/rotate [zerg_interfaces/action/RotateMotor]
```

查看服务：

```bash
ros2 service list -t | grep zerg_driver
```

## 8. 使用三个 Action

三个 Action 由同一个驱动节点管理，并通过运动锁串行执行。不要并发发送多个运动
Action。

### 8.1 完全张开

固定目标位置为 `20 mm`：

```bash
ros2 action send_goal /zerg_driver/open \
  zerg_interfaces/action/OpenGripper \
  '{speed_mm_s: 20.0, current_a: 0.2}' \
  --feedback
```

Goal 参数：

| 参数 | 范围 | 说明 |
| --- | --- | --- |
| `speed_mm_s` | `1 ~ 100 mm/s` | 张开速度，传 0 或负数使用默认值 |
| `current_a` | `0.1 ~ 0.5 A` | 夹持电机电流上限，传 0 或负数使用默认值 |

### 8.2 完全闭合

执行前确认两个夹指之间没有物体，固定目标位置为 `0 mm`：

```bash
ros2 action send_goal /zerg_driver/close \
  zerg_interfaces/action/CloseGripper \
  '{speed_mm_s: 20.0, current_a: 0.2}' \
  --feedback
```

如果夹指在到达 `0 mm` 前接触物体，设备会返回“夹持中/受阻”。由于这个 Action
的语义是“完全闭合”，驱动会将其判定为失败，而不是成功夹取。

### 8.3 有符号相对旋转

旋转 Action 始终执行相对旋转：

- 正数：顺时针。
- 负数：逆时针。
- `720`：顺时针两圈。
- `-360`：逆时针一圈。

首次测试建议使用小角度：

```bash
ros2 action send_goal /zerg_driver/rotate \
  zerg_interfaces/action/RotateMotor \
  '{angle_deg: 30.0, speed_deg_s: 90.0, current_a: 0.3}' \
  --feedback
```

顺时针两圈：

```bash
ros2 action send_goal /zerg_driver/rotate \
  zerg_interfaces/action/RotateMotor \
  '{angle_deg: 720.0, speed_deg_s: 360.0, current_a: 0.5}' \
  --feedback
```

逆时针一圈：

```bash
ros2 action send_goal /zerg_driver/rotate \
  zerg_interfaces/action/RotateMotor \
  '{angle_deg: -360.0, speed_deg_s: 360.0, current_a: 0.5}' \
  --feedback
```

Goal 参数：

| 参数 | 范围 | 说明 |
| --- | --- | --- |
| `angle_deg` | `-36000 ~ 36000°` | 本次相对旋转角度 |
| `speed_deg_s` | `1 ~ 1080°/s` | 旋转速度，传 0 或负数使用默认值 |
| `current_a` | `0.2 ~ 1.0 A` | 旋转电机电流上限，传 0 或负数使用默认值 |

Action 超时默认为 15 秒。应满足：

```text
motion_timeout_s > abs(angle_deg) / speed_deg_s
```

执行低速多圈旋转时，需要适当增大配置文件中的 `motion_timeout_s`，否则设备可能仍在
运动，但 ROS Action 会先因超时结束。

电流越大，允许的夹持力或旋转扭矩通常越大，同时发热和机械冲击也会增加。厂商
手册没有提供电流到夹持力或扭矩的精确换算关系，应从较低电流开始测试。

## 9. Action Feedback 和 Result

### 9.1 张开和闭合

Feedback：

```text
position_mm：当前夹持位置
status：当前夹持状态码
```

Result：

```text
success：是否完成目标
message：结果说明
final_position_mm：结束时的位置
status：结束时的状态码
```

### 9.2 旋转角度为什么一直累加

旋转 Feedback 中的 `angle_deg` 当前表示设备的多圈累计角度，而不是本次 Action
从 0 开始的进度。

设备内部有两个不同概念：

```text
相对旋转命令寄存器 0x0014：写入本次相对角度，设备接收后归零
旋转角度反馈寄存器 0x004A：保存累计多圈角度，不随每次 Action 清零
```

例如当前累计角度为 `720°`，再发送相对 `+360°`，反馈会从 `720°` 增长到
`1080°`，而不是从 `0°` 增长到 `360°`。

设备这样设计是为了保存多圈位置和总圈数。不要在每个 Action 后自动复位多圈值，
否则会丢失累计位置。`/joint_states` 中的旋转位置同样使用该累计角度换算成弧度。

## 10. 状态码

夹持状态：

| 状态码 | 含义 |
| ---: | --- |
| `0` | 到位 |
| `1` | 运动中 |
| `2` | 夹持中/受阻 |
| `3` | 掉落 |

旋转状态：

| 状态码 | 含义 |
| ---: | --- |
| `0` | 到位 |
| `1` | 旋转中 |
| `2` | 旋转受阻 |
| `3` | 曾受阻但到位/掉落 |
| `4` | 堵转停转 |

旋转 Action 收到 `2`、`3` 或 `4` 时会返回失败。例如：

```text
success: false
message: blocked
status: 2
```

此时先检查夹爪负载、线缆缠绕和机械干涉，不要直接反复提高电流。

## 11. Service

### 11.1 手动初始化

初始化会让夹指向外运动，执行前确保行程内没有障碍物：

```bash
ros2 service call /zerg_driver/initialize \
  std_srvs/srv/Trigger '{}'
```

### 11.2 电机使能

使能：

```bash
ros2 service call /zerg_driver/enable \
  std_srvs/srv/SetBool '{data: true}'
```

关闭电机输出：

```bash
ros2 service call /zerg_driver/enable \
  std_srvs/srv/SetBool '{data: false}'
```

关闭电机输出可能导致负载失去保持力，执行前应确保机构和负载安全。

## 12. 状态监控

查看一次诊断信息：

```bash
ros2 topic echo /diagnostics --once
```

正常状态示例：

```text
message: ready
hardware_id: modbus:1@/dev/ttyUSB0
initialization_code: 5
grip_status: 0
rotation_status: 0
error_flags: 0x00000000
```

持续查看关节状态：

```bash
ros2 topic echo /joint_states
```

`JointState` 使用 ROS SI 单位：

- 夹持位置：米。
- 夹持速度：米/秒。
- 旋转位置：弧度。
- 旋转速度：弧度/秒。

## 13. 在其他 ROS 2 工作区部署

假设目标工作区为 `~/robot_ws`。

### 13.1 安装 SDK

SDK 可以保留在当前目录并以可编辑方式安装：

```bash
python3 -m pip install --user -e /home/sxkc/ZERG-SDK/zerg_sdk
```

### 13.2 复制 ROS 2 包

```bash
mkdir -p ~/robot_ws/src
cp -r /home/sxkc/ZERG-SDK/zerg_interfaces ~/robot_ws/src/
cp -r /home/sxkc/ZERG-SDK/zerg_ros2_driver ~/robot_ws/src/
```

不要复制 `build/`、`install/` 和 `log/`。

### 13.3 编译目标工作区

```bash
cd ~/robot_ws
source /opt/ros/humble/setup.bash

rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install \
  --packages-select zerg_interfaces zerg_ros2_driver

source install/setup.bash
```

然后使用与本文相同的 launch 和 Action 命令。

## 14. 更新代码后的操作

修改纯 Python SDK 后，由于使用了 `pip -e` 可编辑安装，通常无需重新安装。

修改以下内容后需要重新执行 `colcon build`：

- `.action` 接口定义。
- `package.xml`。
- `CMakeLists.txt`。
- ROS 包安装文件或入口点。

推荐命令：

```bash
cd /home/sxkc/ZERG-SDK
source /opt/ros/humble/setup.bash

colcon build --symlink-install \
  --packages-select zerg_interfaces zerg_ros2_driver

source install/setup.bash
```

每个新终端都必须重新执行 `source`。

## 15. 测试

运行不需要真实硬件的 SDK 测试：

```bash
cd /home/sxkc/ZERG-SDK
PYTHONPATH=zerg_sdk python3 -m unittest discover -s zerg_sdk/test -v
```

测试覆盖：

- Modbus CRC。
- 手册中的初始化、旋转和状态读取报文。
- 大小端浮点转换。
- Modbus 异常响应。
- 参数范围检查。
- 状态反馈解析。
- 点位编码。

## 16. 常见故障排查

### 16.1 `ModuleNotFoundError: No module named 'zerg_sdk'`

SDK 没有安装或当前 Python 环境找不到它：

```bash
python3 -m pip install --user -e /home/sxkc/ZERG-SDK/zerg_sdk
python3 -m pip show zerg-sdk
```

临时方式：

```bash
export PYTHONPATH=/home/sxkc/ZERG-SDK/zerg_sdk:$PYTHONPATH
```

### 16.2 `zerg_sdk.__file__` 输出 `None`

在 `/home/sxkc/ZERG-SDK` 根目录直接导入时，Python 可能先看到外层同名目录。
切换到其他目录验证：

```bash
cd /tmp
python3 -c "import zerg_sdk; print(zerg_sdk.__file__)"
```

### 16.3 `Permission denied: /dev/ttyUSB0`

```bash
sudo usermod -aG dialout "$USER"
```

注销并重新登录。确认：

```bash
groups
ls -l /dev/ttyUSB0
```

### 16.4 找不到 `/dev/ttyUSB0`

```bash
lsusb
sudo dmesg -w
```

重新拔插 CH340。检查是否被 BRLTTY 抢占。

### 16.5 Action Server 一直不可用

确认驱动节点正在运行：

```bash
ros2 node list
ros2 action list -t
```

两个终端都必须 source 同一个 ROS 2 工作区。

### 16.6 驱动不断重连

依次检查：

- 串口设备名是否正确。
- 当前用户是否具有串口权限。
- 是否有其他程序占用 `/dev/ttyUSB0`。
- RS485 A/B 是否接反。
- 夹爪和转接器是否共地。
- 波特率是否为 115200。
- 设备 ID 是否为 1。

检查占用串口的进程：

```bash
lsof /dev/ttyUSB0
```

### 16.7 旋转返回 `blocked`

`status: 2` 表示设备检测到旋转受阻。检查机械干涉、负载、线缆缠绕和电流设置。
排除机械问题后，从较小角度、较低速度开始重新测试。

## 17. 安全注意事项

- 首次动作应使用小行程、小角度、低速度和较低电流。
- 完全闭合前确保夹指之间没有人体、工具或产品。
- 多圈旋转前确保电源线和通信线不会缠绕。
- Action 取消只会结束 ROS Action；设备协议没有通用急停指令，不能假设取消会立即
  停止物理运动。
- 相对旋转命令不会自动重试。通信结果不明确时自动重试可能导致重复旋转。
- 不要在实时运动过程中保存设备参数。
- 同一时刻只能有一个程序访问 `/dev/ttyUSB0`。

## 18. 日常使用最简流程

终端 1：

```bash
cd /home/sxkc/ZERG-SDK
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch zerg_ros2_driver zerg_driver.launch.py
```

终端 2：

```bash
source /opt/ros/humble/setup.bash
source /home/sxkc/ZERG-SDK/install/setup.bash

ros2 action list -t
```

然后根据需要调用 `/zerg_driver/open`、`/zerg_driver/close` 或
`/zerg_driver/rotate`。

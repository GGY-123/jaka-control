# JAKA Mini 2 Linux Python SDK 测试工程

本工程已经包含你从 JAKA 官网下载的 Linux x86_64 Python SDK，可用于 Ubuntu x86_64、Python 3.10.12 环境。

已筛选并重命名的文件：

```text
sdk/jkrc.so          # Python 扩展，ELF 64 位 x86-64
sdk/libjakaAPI.so    # JAKA 动态库，ELF 64 位 x86-64
sdk/jkrc.pyi         # Python 接口提示
sdk/changelog
```

不要把 `.dll`、`.pyd`、`.lib` 或 `.exp` 传到 Linux；它们是 Windows 文件。ARM64 和 32 位 x86 的 `.so` 也不能用于这台电脑。

## 1. 从 Windows 补传 SDK 文件

如果工程已经位于 Linux 主目录 `~/JAKA_Mini2_Python_Test`，在 Windows PowerShell 执行：

```powershell
scp -r "C:\Users\Administrator\Documents\Codex\2026-08-20\zhe\outputs\JAKA_Mini2_Python_Test\sdk" 用户名@Linux电脑IP:~/JAKA_Mini2_Python_Test/
```

把 `用户名` 和 `Linux电脑IP` 替换成实际值。若要传整个最新版工程：

```powershell
scp -r "C:\Users\Administrator\Documents\Codex\2026-08-20\zhe\outputs\JAKA_Mini2_Python_Test" 用户名@Linux电脑IP:~/
```

## 2. 在 Linux 上检查文件

```bash
cd ~/JAKA_Mini2_Python_Test
ls -lh sdk
file sdk/jkrc.so sdk/libjakaAPI.so
ldd sdk/jkrc.so
ldd sdk/libjakaAPI.so
```

`file` 应显示 `ELF 64-bit` 和 `x86-64`。如果 `ldd` 显示 `not found`，先不要控制机械臂，需补齐缺少的运行库。

## 3. 创建运行环境

```bash
cd ~/JAKA_Mini2_Python_Test
sudo apt update
sudo apt install -y python3-venv
python3 -m venv .venv
chmod +x run.sh check_environment.py jaka_mini2_test.py
```

先验证 Python 能否加载 SDK：

```bash
export PYTHONPATH="$PWD/sdk"
export LD_LIBRARY_PATH="$PWD/sdk${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
.venv/bin/python check_environment.py
```

成功时应看到 `jkrc import: OK`。如果报 Python ABI 或 `undefined symbol`，请保留完整错误信息；虽然 CPU 架构已匹配，仍需根据错误确认此 `jkrc.so` 是否兼容 Python 3.10。

## 4. 网络和机械臂准备

假设机械臂控制器 IP 为 `192.168.2.64`：

```bash
ping -c 4 192.168.2.64
```

Linux 网卡与机械臂应在同一网段且 IP 不重复。在 JAKA App 中切换控制源为 SDK，释放急停并清除报警。实际运动前清空工作区，确保急停按钮可立即触及。

## 5. 先运行只读测试

旧控制器或无需账号时：

```bash
cd ~/JAKA_Mini2_Python_Test
./run.sh --ip 192.168.2.64
```

V3 控制器使用 gRPC 和 SDK 账号时：

```bash
./run.sh --ip 192.168.2.64 --grpc --username jaka_sdk
```

程序会提示输入密码。只读测试仅登录、读取版本、关节角和状态并登出，不会上电、使能或运动。

## 6. 小幅运动测试

确认现场安全后，以 J1 相对移动 2 度、速度 2 度/秒为例：

```bash
./run.sh \
  --ip 192.168.2.64 \
  --grpc \
  --username jaka_sdk \
  --joint 1 \
  --move-relative-deg 2 \
  --speed-deg-s 2 \
  --execute
```

程序还会要求输入大写 `MOVE` 才会执行。测试程序限制最大相对位移为 5 度、最大速度为 5 度/秒。

## 7. 常见问题

- `No such file or directory: sdk`：没有进入工程目录，先执行 `cd ~/JAKA_Mini2_Python_Test`。
- `No module named jkrc`：通过 `run.sh` 启动，或设置上面的 `PYTHONPATH`。
- `libjakaAPI.so: cannot open shared object file`：通过 `run.sh` 启动，或设置上面的 `LD_LIBRARY_PATH`。
- 登录失败：确认电脑能 ping 通控制器、JAKA App 控制源为 SDK，并检查 gRPC、账号和密码。
- 运动失败：检查急停、报警、上电/使能状态、控制权和安全区配置。

## 8. 持续运行说明

当前 `jaka_mini2_test.py` 是一次性测试程序，完成后会退出。如果后续要一直等待 HTTP 请求，应运行独立 HTTP 服务，并用 systemd 管理开机启动和异常重启。

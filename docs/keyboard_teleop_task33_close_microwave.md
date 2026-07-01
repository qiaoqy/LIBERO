# Task 33 关闭微波炉键盘遥操采集指南

这份文档记录如何在本仓库中启动 LIBERO task 33，也就是 `close the microwave`，并使用键盘遥操采集人工 demo。

## 环境状态

本机已经创建好 conda 环境：

```powershell
conda activate libero
cd C:\workspace\LIBERO
```

如果 PowerShell 找不到 `conda`，先加载 conda 的 PowerShell hook：

```powershell
& C:\ProgramData\miniconda3\shell\condabin\conda-hook.ps1
conda activate libero
```

这个环境使用 Python 3.8.13，并且当前仓库已经用 editable 模式安装进环境。`editable` 模式对应 `pip install -e .`，意思是 conda 环境里的 `libero` 包不会复制一份固定快照到 `site-packages`，而是直接链接到当前仓库源码目录 `C:\workspace\LIBERO`。这样你修改仓库里的 Python 文件后，不需要重新 `pip install`，下次运行脚本会直接使用修改后的源码；它适合开发和调试本地仓库。

为了让 Windows GUI 遥操能正常导入 `robosuite`，本机还做了这些修补：

- 已创建 `C:\tmp`，因为 `robosuite` 在 Windows 下会写 `C:\tmp\robosuite.log`。
- 已将 `C:\Users\qqy\.conda\envs\libero\Lib\site-packages\mujoco\mujoco.dll` 复制到 `C:\Users\qqy\.conda\envs\libero\Lib\site-packages\robosuite\utils\mujoco.dll`。
- 已把 `C:\Users\qqy\.conda\envs\libero\Lib\site-packages\robosuite\macros.py` 里的 `MUJOCO_GPU_RENDERING` 改成 `False`，避免 Windows 下强制使用不支持的 `egl` 后端。
- 已安装 `pynput`，这是 `robosuite.devices.Keyboard` 需要的键盘输入依赖。
- 已安装 `pygame==2.6.1`，这是当前自定义 `--device gamepad` 手柄遥操支持使用的输入依赖。

## 当前渲染和 GPU 说明

当前键盘遥操命令使用 `$env:MUJOCO_GL = "glfw"`，并打开 `has_renderer=True` 的 MuJoCo viewer。这是可见窗口渲染路径，通常会通过 Windows 的 OpenGL 驱动使用本机显卡做硬件加速，但它不是 CUDA/EGL 离屏渲染路径，也不会使用 `MUJOCO_EGL_DEVICE_ID` 来指定某张 CUDA GPU。

已实测：当前命令可以弹出渲染窗口并进行键盘遥操。旧版 robosuite / MuJoCo viewer 默认窗口标题会显示为 `offscreen render`，这个名字容易误导，但不代表本条采集命令正在走 LIBERO 的 `OffScreenRenderEnv`。对 `scripts\collect_demonstration.py` 来说，环境参数是 `has_renderer=True`、`has_offscreen_renderer=False`，所以这是可交互的前台 viewer。

为了便于调试，采集脚本现在会把窗口标题改成 `LIBERO Teleop - close the microwave`。你也可以通过 `--window-title` 自定义标题。

之前把 `robosuite` 的 `MUJOCO_GPU_RENDERING` 改成 `False`，是因为 `robosuite==1.4.0` 在 Windows 下会强制设置 `MUJOCO_GL=egl`，而该版本 Windows 分支不接受 `egl`，会在导入阶段报错。对现在的键鼠采集窗口来说，应该使用 `glfw`；如果之后要跑大规模离屏相机渲染或训练评估，建议放到 Linux/WSL + EGL 环境里处理。

注意：`robomimic==0.2.0` 在这个 Windows 环境里没有完整安装，因为它会拉取 `egl-probe`，而 `egl-probe` 的构建脚本调用 Unix 的 `make -j`，会在 Windows 下失败。这不影响 `scripts/collect_demonstration.py` 采集人工 demo；如果后续要跑完整训练流程，建议在 Linux/WSL 环境里单独处理 robomimic。

## 任务信息

`libero_90` 的 task id 是从 0 开始计数的。`task_id=33` 对应：

```text
任务名: KITCHEN_SCENE6_close_the_microwave
语言指令: close the microwave
BDDL: libero\libero\bddl_files\libero_90\KITCHEN_SCENE6_close_the_microwave.bddl
```

采集脚本没有 `--task-id` 参数，它接收的是 BDDL 文件路径，所以启动 task 33 时要直接传上面的 BDDL 文件。

## 启动采集

在 PowerShell 中从仓库根目录运行：

```powershell
conda activate libero
cd C:\workspace\LIBERO

$env:MUJOCO_GL = "glfw"
Remove-Item Env:\MUJOCO_EGL_DEVICE_ID -ErrorAction SilentlyContinue

python scripts\collect_demonstration.py `
  --device keyboard `
  --robots Panda `
  --bddl-file libero\libero\bddl_files\libero_90\KITCHEN_SCENE6_close_the_microwave.bddl `
  --num-demonstration 10 `
  --directory demonstration_data `
  --camera agentview `
  --controller OSC_POSE `
  --pos-sensitivity 1.5 `
  --rot-sensitivity 1.0 `
  --window-title "LIBERO Teleop - Task 33 Close Microwave"
```

把 `--num-demonstration 10` 改成你想采集的成功轨迹数量。脚本会一直循环，直到保存够指定数量的成功 demo。

如果当前终端激活 conda 不方便，可以用下面这条等价命令：

```powershell
$env:MUJOCO_GL = "glfw"
Remove-Item Env:\MUJOCO_EGL_DEVICE_ID -ErrorAction SilentlyContinue

& C:\Windows\System32\cmd.exe /c "call C:\ProgramData\miniconda3\Scripts\activate.bat libero && python -u scripts\collect_demonstration.py --device keyboard --robots Panda --bddl-file libero\libero\bddl_files\libero_90\KITCHEN_SCENE6_close_the_microwave.bddl --num-demonstration 10 --directory demonstration_data --camera agentview --controller OSC_POSE --pos-sensitivity 1.5 --rot-sensitivity 1.0 --window-title ""LIBERO Teleop - Task 33 Close Microwave"""
```

## 键鼠操作

启动后会弹出 MuJoCo viewer。窗口标题应显示为 `LIBERO Teleop - Task 33 Close Microwave`；如果没有传 `--window-title`，默认是 `LIBERO Teleop - close the microwave`。先点击 viewer 窗口，让它获得键盘焦点。机器人动作由键盘控制；鼠标主要用于聚焦窗口或调整 viewer 视角，不直接控制机械臂。

| 按键 | 动作 |
| --- | --- |
| `w` / `s` | 末端执行器沿 x 方向移动 |
| `a` / `d` | 末端执行器沿 y 方向移动 |
| `r` / `f` | 末端执行器上 / 下移动 |
| `z` / `x` | 绕 x 轴旋转 |
| `t` / `g` | 绕 y 轴旋转 |
| `c` / `v` | 绕 z 轴旋转 |
| `space` | 切换夹爪开 / 合 |
| `q` | 中止并丢弃当前 episode |
| `ESC` | 停止采集并关闭渲染窗口 |

对 `close the microwave` 这个任务，常规流程是把夹爪移动到微波炉门把手附近，必要时闭合夹爪，然后推动或拉动门把手直到微波炉关闭。任务成功后保持最终状态一小会儿；脚本会在 `env._check_success()` 连续为真 10 个控制步之后保存该条轨迹。

关闭窗口有三种常用情况：

- 想丢弃当前这条 demo 但继续采集下一条：按 `q`。
- 想停止整个采集并关闭渲染窗口：在 viewer 窗口聚焦时按 `ESC`。
- 如果键盘焦点不在 viewer 或窗口没有响应：回到启动脚本的终端按 `Ctrl+C`。

## 输出文件

成功 demo 会被聚合保存到：

```text
demonstration_data\<domain>_ln_<problem>_<timestamp>_close_the_microwave\demo.hdf5
```

例如这次采集到的两条 demo 实际保存在：

```text
demonstration_data\robosuite_ln_libero_kitchen_tabletop_manipulation_1782812599_4388041_close_the_microwave\demo.hdf5
```

这个 HDF5 里包含 `data/demo_1` 和 `data/demo_2`，两条轨迹长度分别是 1472 和 1481 步。

原始逐步采集文件会暂存在：

```text
demonstration_data\tmp\...
```

按 `q` 中止的 episode 会被排除，不会计入最终 `demo.hdf5`。

## 渲染采集结果为视频

可以把 raw `demo.hdf5` 回放成 H.264 mp4，方便在 VS Code 或浏览器里直接预览采集质量。这个脚本默认调用 `ffmpeg`，输出 `h264/yuv420p`，兼容性比 OpenCV 的 `mp4v` 更好。

```powershell
conda activate libero
cd C:\workspace\LIBERO

$env:MUJOCO_GL = "glfw"

python scripts\render_collected_demo_video.py `
  --demo-file demonstration_data\robosuite_ln_libero_kitchen_tabletop_manipulation_1782812599_4388041_close_the_microwave\demo.hdf5 `
  --camera agentview `
  --height 256 `
  --width 256 `
  --fps 20 `
  --stride 1
```

默认输出到同级 `videos` 目录。当前这次已经生成：

```text
demonstration_data\robosuite_ln_libero_kitchen_tabletop_manipulation_1782812599_4388041_close_the_microwave\videos\demo_1_agentview.mp4
demonstration_data\robosuite_ln_libero_kitchen_tabletop_manipulation_1782812599_4388041_close_the_microwave\videos\demo_2_agentview.mp4
```

如果只想快速预览，可以把 `--stride` 改成 `2` 或 `4`，视频帧数会减少，渲染更快。

当前两条视频已重新渲染为 H.264：

```text
demo_1_agentview.mp4: h264, yuv420p, 256x256, 20 FPS, 1472 frames
demo_2_agentview.mp4: h264, yuv420p, 256x256, 20 FPS, 1481 frames
```

## 转成 LIBERO 训练数据格式

采集完成后，可以把 raw `demo.hdf5` 转成 LIBERO 训练代码常用的数据集格式：

```powershell
conda activate libero
cd C:\workspace\LIBERO

$env:MUJOCO_GL = "glfw"
Remove-Item Env:\MUJOCO_EGL_DEVICE_ID -ErrorAction SilentlyContinue

python scripts\create_dataset.py `
  --demo-file demonstration_data\<你的输出文件夹>\demo.hdf5 `
  --use-camera-obs
```

这里的 `<你的输出文件夹>` 替换成 `collect_demonstration.py` 实际打印或生成的输出目录。

转换后的文件会按照 `~\.libero\config.yaml` 中的 datasets 路径保存。当前本机默认配置下，预期输出路径是：

```text
C:\workspace\LIBERO\libero\libero\datasets\libero_90\KITCHEN_SCENE6_close_the_microwave_demo.hdf5
```

## 快速检查

检查 task 33 映射：

```powershell
$env:MUJOCO_GL = "glfw"
python -c "from libero.libero import benchmark; b=benchmark.get_benchmark_dict()['libero_90'](); t=b.get_task(33); print(t.name); print(t.language)"
```

期望输出：

```text
KITCHEN_SCENE6_close_the_microwave
close the microwave
```

检查采集脚本入口：

```powershell
$env:MUJOCO_GL = "glfw"
python scripts\collect_demonstration.py --help
```

## Task 33 反向恢复任务采集

正向 task 33 的测试采集已经完成。下一步采集的是反向恢复任务：从 `close the microwave` 执行完成后的场景出发，通过键盘遥操把场景恢复到接近官方正向 demo 起点的状态，也就是把微波炉重新恢复到 task 33 开始前的样子。

### 目标定义

- 官方 task 33 正向 demo 有 50 条，因此反向恢复任务也计划采集 50 条。
- 第 `i` 条反向 demo 使用官方第 `i` 条正向 demo 的最后一帧作为初始状态。
- 第 `i` 条反向 demo 的完成目标是恢复到接近官方第 `i` 条正向 demo 的第一帧状态。
- 数据编号必须一一对应，避免把不同官方 demo 的首帧和末帧混用。

### 官方数据位置

官方示例数据目录是：

```text
data\libero_official\libero_90
```

task 33 对应的官方数据文件预期是：

```text
data\libero_official\libero_90\KITCHEN_SCENE6_close_the_microwave_demo.hdf5
```

该文件已经下载并保存完成。已检查到 HDF5 中有 50 个 `data/demo_*`，编号从 `demo_0` 到 `demo_49`。每个 demo 里包含 `model_file`、`states`、`actions` 等反向初始化需要的字段。

检查命令：

```powershell
conda activate libero
cd C:\workspace\LIBERO

python -c "import h5py; f=h5py.File(r'data\libero_official\libero_90\KITCHEN_SCENE6_close_the_microwave_demo.hdf5','r'); demos=sorted(f['data'].keys()); print(len(demos)); print(demos[:3], demos[-3:]); d=f['data'][demos[0]]; print(d.attrs.keys()); print(d['states'].shape, d['actions'].shape)"
```

本机检查结果：

```text
exists True
size_bytes 1009177536
demo_count 50
first_demos ['demo_0', 'demo_1', 'demo_2', 'demo_3', 'demo_4']
last_demos ['demo_45', 'demo_46', 'demo_47', 'demo_48', 'demo_49']
demo_attrs ['init_state', 'model_file', 'num_samples']
datasets ['actions', 'dones', 'obs', 'rewards', 'robot_states', 'states']
states_shape (236, 47)
actions_shape (236, 7)
data_attrs ['bddl_file_name', 'env_args', 'env_name', 'macros_image_convention', 'num_demos', 'problem_info', 'tag', 'total']
```

这里的 `states_shape` 和 `actions_shape` 是 `demo_0` 的形状，其他 demo 的轨迹长度可能不同，但 state 维度应保持一致。

### 初始化思路

官方 demo 的 HDF5 每条轨迹里通常包含：

- `data/demo_i.attrs["model_file"]`：该条 demo 对应的 MuJoCo XML 场景。
- `data/demo_i/states`：每一帧的 flattened MuJoCo state。
- `data/demo_i/actions`：正向任务动作序列。

反向任务采集时，不能只使用原始 task 33 BDDL 的默认 reset 状态；需要对每一条反向 episode 做对应初始化：

1. 读取官方 `demo_i` 的 `model_file`。
2. 读取官方 `demo_i/states[-1]` 作为反向 episode 的初始 MuJoCo state。
3. `env.reset_from_xml_string(model_file)` 后调用 `env.sim.set_state_from_flattened(states[-1])` 和 `env.sim.forward()`。
4. 开始键盘遥操，从微波炉已关闭状态恢复到接近 `states[0]`。

这里说的“用官方 task 33 的最后一帧的 BDDL 做场景初始化”，在实现层面更准确地说是使用官方 demo 中保存的 `model_file` 场景 XML 加上最后一帧 MuJoCo state 初始化。实验场景和 object list 复用原本正向数据的场景 XML；场景中物体的位置、关节状态和其他 MuJoCo state 属性按照对应官方 demo 的 `states[-1]` 设置。BDDL 仍然用来标识任务和物体语义，但每条 demo 的精确初始姿态来自 HDF5 state。

### 成功判定计划

当前 `scripts\collect_demonstration.py` 使用的是原始 task 33 的 `env._check_success()`，它判断的是“微波炉已经关闭”。反向任务的目标相反，所以不能直接沿用这个成功条件。

反向成功判定先按两层做：

1. 人工主判定：操作者把微波炉恢复到接近官方 `states[0]` 的视觉状态后，按 `p` 保存当前 episode。
2. 程序辅助判定：记录当前 state 与官方 `states[0]` 的差异，尤其关注微波炉门关节、相关物体位姿和机器人末端位置；后续根据实际 state 字段再设阈值。

当前已经先实现人工确认保存，因为这样最贴近当前键盘采集流程，也避免在没有确认 MuJoCo state 各字段含义前写错自动成功条件。等能稳定采集和回放后，再把门关节角度等关键指标加入自动判定。

### 当前 demo 0 反向采集脚本

当前采集脚本 `scripts\collect_demonstration.py` 每次 episode 都调用普通 `env.reset()`，并且只按原 task 的 `_check_success()` 保存。因此已经新增一个 demo 0 专用反向采集脚本：

```text
scripts\collect_reverse_demo0.py
```

这个脚本当前支持：

- `--reference-demo-file`：官方 task 33 HDF5 路径。
- `--source-demo-name`：默认 `demo_0`，当前先采官方 `demo_0` 的反向数据。
- `--directory`：反向 demo 输出目录。
- `--device`：支持 `keyboard` 或 `gamepad`。`gamepad` 通过 `pygame` 读取 PS5 / Xbox 等 SDL 能识别的手柄。
- `--camera`、`--controller`、`--pos-sensitivity`、`--rot-sensitivity`、`--window-title`：沿用当前采集参数。
- `--save-key`：默认 `p`，用于人工确认保存。
- `--goal-overlay-alpha`：默认 `0.3`，在遥操窗口上叠加官方首帧目标图像。
- `--viewer-scale`：默认 `1.5`，把 OpenCV 遥操窗口放大约 1.5 倍，便于观察目标蒙版和微波炉门状态。
- `--disable-goal-overlay`：关闭目标蒙版。
- `--start-action-threshold`：默认 `1e-6`，用于跳过开始操作前的空等待帧。
- 开始前打印官方 demo 名称、官方 state/action 形状、反向初始 state index 和目标 state index。
- 支持按 `p` 保存成功，按 `q` 丢弃当前 episode，按 `ESC` 停止整个采集。

输出文件会单独放在：

```text
demonstration_data_reverse\<domain>_ln_<problem>_reverse_demo_0_<timestamp>\demo.hdf5
```

每条反向 demo 的 HDF5 metadata 里会额外记录：

- `source_demo_file`：官方 HDF5 文件路径。
- `source_demo_name`：例如 `demo_0`。
- `source_init_state_index`：固定为官方正向 demo 的最后一帧索引。
- `source_goal_state_index`：固定为 `0`。
- `reverse_task_language`：例如 `restore the microwave to the initial open state`。
- `source_init_state`：官方正向 demo 的最后一帧 state，也就是反向 demo 的初始状态。
- `source_goal_state`：官方正向 demo 的第一帧 state，也就是反向恢复目标参考。

### 采集流程

当前流程是：

1. 官方 task 33 文件已经确认完整，有 50 条 demo。
2. `scripts\collect_reverse_demo0.py` 已经完成 `demo_0` 冒烟采集。
3. `demo_0` 反向采集结果已经渲染为视频，可用于检查初始化、键盘控制和保存逻辑。
4. 下一步使用 `scripts\collect_reverse_demonstrations.py` 采集 `demo_0` 到 `demo_49` 的 50 条完整反向数据；每条反向 demo 都从对应官方 demo 的最后一帧开始。
5. 采集完成后统一渲染视频做质量检查。
6. 如果训练代码需要 LIBERO 标准数据格式，再单独写转换脚本或扩展 `scripts\create_dataset.py`，把反向任务保存为新的数据集文件。

### 采集 demo 0 反向数据

运行：

```powershell
conda activate libero
cd C:\workspace\LIBERO

$env:MUJOCO_GL = "glfw"
Remove-Item Env:\MUJOCO_EGL_DEVICE_ID -ErrorAction SilentlyContinue

python scripts\collect_reverse_demo0.py `
  --device keyboard `
  --robots Panda `
  --bddl-file libero\libero\bddl_files\libero_90\KITCHEN_SCENE6_close_the_microwave.bddl `
  --reference-demo-file data\libero_official\libero_90\KITCHEN_SCENE6_close_the_microwave_demo.hdf5 `
  --source-demo-name demo_0 `
  --directory demonstration_data_reverse `
  --camera agentview `
  --controller OSC_POSE `
  --pos-sensitivity 2.0 `
  --rot-sensitivity 1.0 `
  --goal-overlay-alpha 0.3 `
  --viewer-scale 1.5 `
  --start-action-threshold 1e-6 `
  --save-key p `
  --window-title "LIBERO Teleop - Task 33 Reverse Demo 0"
```

启动后会先用同一个遥操相机视角渲染官方 `demo_0` 的第一帧，作为透明度 30% 的目标蒙版；然后把环境初始化到官方 `demo_0` 的最后一帧，也就是微波炉已经关闭后的状态。操作者一边看当前画面和目标蒙版的叠加图，一边用键盘把场景恢复到接近官方 `demo_0` 第一帧：

- 按 `p`：人工确认当前 episode 成功并保存。
- 按 `q`：丢弃当前 episode，不保存。
- 按 `ESC`：停止采集并关闭渲染窗口。

脚本现在会跳过正式操作前的等待帧：环境虽然已经显示并可观察，但在检测到第一条有效键盘输入前不会调用 `env.step()`，因此 `DataCollectionWrapper` 不会开始写 episode。第一条有效输入包括：

- 位姿控制 action 的前 6 维范数大于 `--start-action-threshold`，也就是 `w/a/s/d/r/f/z/x/t/g/c/v` 等移动或旋转输入。
- 夹爪状态第一次切换，也就是按 `space`。

HDF5 里的 `states[0]` 仍然遵循 robosuite / LIBERO 的标准语义：它是第一条 action 执行前的状态；区别是现在不会包含你观察窗口、准备操作时产生的空等候控制步。

`--pos-sensitivity` 在脚本里定义为命令行参数，并传给 `robosuite.devices.Keyboard(pos_sensitivity=...)`。键盘每次位置按键会先改变一个内部位置增量：

```text
w/s/a/d/r/f -> 0.05 * pos_sensitivity
```

随后 `input2action()` 对 OSC_POSE 控制器还会把键盘的 `dpos` 乘以 75，作为环境的平移控制 action。因此 `--pos-sensitivity` 控制的是键盘平移输入的放大倍数；数值越大，按同样的键机械臂末端平移命令越大，移动会更快，但也更容易过冲、撞物体或难以精细对齐。`--rot-sensitivity` 类似地控制旋转按键 `z/x/t/g/c/v` 的放大倍数。

### PS5 / 游戏手柄遥操

当前已给反向采集脚本添加 `--device gamepad`。这个模式使用 `pygame` 读取手柄模拟轴，比 robosuite 自带键盘模式更连续，适合减少“按一下动一下”的离散运动。

默认映射按常见 SDL / pygame PS5 手柄布局设置：

| 输入 | 动作 |
| --- | --- |
| 左摇杆 x / y | 末端执行器 x / y 平移；左右方向已实测正确，前后方向已按当前坐标系修正正负号 |
| 右摇杆上 / 下 | 末端执行器上 / 下移动；上推右摇杆时机械臂向上走 |
| 按住 `Circle` + 右摇杆上 / 下 | `OSC_POSE` 旋转 action 的 x 轴正 / 负方向 |
| 按住 `Circle` + 右摇杆左 / 右 | `OSC_POSE` 旋转 action 的 z 轴正 / 负方向；因为 robosuite 会翻转 z，右推对应 z 负方向 |
| 按住 `Circle` + 左摇杆左 / 右 | `OSC_POSE` 旋转 action 的 x 轴负 / 正方向；这套轴已和旧版本交换 |
| 按住 `Circle` + 左摇杆上 / 下 | `OSC_POSE` 旋转 action 的 y 轴正 / 负方向；这套轴已和旧版本交换 |
| `Triangle` | 切换夹爪开 / 合 |
| `Cross` | 删除刚才保存的上一条 demo，并回到上一条重新采集 |
| 短按 `Square` | 保存当前 episode，并震动 1 次提示 |
| 长按 `Square` | 超过长按阈值后开始持续震动；松开 `Square` 时停止震动，丢弃当前 episode、reset 场景并自动重新开始当前编号 |
| `Options` | reset 当前 episode，不保存并自动重新开始当前编号 |
| `Share` | 停止整轮采集 |

启动时脚本会打印检测到的手柄名称、axis 数量、button 数量。如果你的 PS5 手柄在 Windows / pygame 下编号不同，可以用这些参数改映射：

```text
--gamepad-axis-left-x
--gamepad-axis-left-y
--gamepad-axis-right-x
--gamepad-axis-right-y
--gamepad-button-gripper
--gamepad-button-rotate-modifier
--gamepad-button-save-discard
--gamepad-button-reset
--gamepad-button-stop
--gamepad-square-long-press-seconds
```

`--viewer-scale 1.5` 会把 robosuite OpenCV viewer 从默认约 `1280x800` 放大到约 `1920x1200`；目标蒙版和当前画面都会用同一窗口尺寸渲染，所以叠加仍然对齐。脚本会显式把 OpenCV 窗口设为 `WINDOW_NORMAL` 并调用 `cv2.resizeWindow`，启动时也会打印类似：

```text
OpenCV viewer size: 1920x1200 (scale=1.5)
```

如果屏幕分辨率或 Windows 缩放导致窗口太大，可以把 `--viewer-scale` 改成 `1.25` 或 `1.3`。

`--gamepad-deadzone` 默认是 `0.08`，用于过滤摇杆漂移。`--gamepad-pos-step` 默认是 `0.01`，`--gamepad-rot-step` 默认是 `0.01`；它们会再乘以 `--pos-sensitivity` / `--rot-sensitivity`。因为 `input2action()` 对非键盘 device 会使用 SpaceMouse 路径的缩放，当前默认值已经按这个路径调小。旋转速度已经比旧版 `0.02` 降低一半，方便精细对齐微波炉门。

手柄多轴输入按向量方式合成，不会互相阻塞。例如左摇杆推到左上 45 度时，会同时产生 x 和 y 两个方向的平移命令，机械臂沿两个方向的合成方向运动。为了避免斜向推杆比单轴推杆更快，脚本会先把 `[x, y, z]` 平移向量做长度限制：如果向量范数大于 1，就归一化到 1；旋转向量也采用同样的限幅逻辑。因此合成方向保留，但最大速度仍受原本单轴最大速度约束。

没有按住 `Circle` 时，左右摇杆只负责平移，不会触发旋转；按住 `Circle` 后，左右摇杆进入旋转层，此时不会触发平移。

用手柄采 `demo_0`：

```powershell
conda activate libero
cd C:\workspace\LIBERO

$env:MUJOCO_GL = "glfw"
Remove-Item Env:\MUJOCO_EGL_DEVICE_ID -ErrorAction SilentlyContinue

python scripts\collect_reverse_demo0.py `
  --device gamepad `
  --robots Panda `
  --bddl-file libero\libero\bddl_files\libero_90\KITCHEN_SCENE6_close_the_microwave.bddl `
  --reference-demo-file data\libero_official\libero_90\KITCHEN_SCENE6_close_the_microwave_demo.hdf5 `
  --source-demo-name demo_0 `
  --directory demonstration_data_reverse `
  --camera agentview `
  --controller OSC_POSE `
  --pos-sensitivity 1.0 `
  --rot-sensitivity 1.0 `
  --goal-overlay-alpha 0.3 `
  --viewer-scale 1.5 `
  --start-action-threshold 1e-6 `
  --gamepad-deadzone 0.08 `
  --gamepad-pos-step 0.01 `
  --gamepad-rot-step 0.01 `
  --gamepad-square-long-press-seconds 0.8 `
  --window-title "LIBERO Teleop - Task 33 Reverse Demo 0 Gamepad"
```

如果移动太慢，优先小幅提高 `--gamepad-pos-step`，例如 `0.012` 或 `0.015`；如果太冲，先降低 `--gamepad-pos-step`，不要只靠大幅改变 `--pos-sensitivity`。

单条 `demo_0` 脚本和 50 条批量脚本现在行为一致：长按 `Square` 或按 `Options` 只会丢弃当前 episode，并重新打开同一个官方 source demo 的末帧场景继续采；不会直接退出脚本。只有保存成功或按 `Share` / `ESC` 停止时才会结束。

`Cross` 只在已经保存过至少一条 demo 后有意义。按下 `Cross` 会撤销刚刚保存的上一条：批量脚本会从输出 HDF5 中删除上一条 `demo_i`，更新 `num_demos` / `total`，并退回到那一条重新采集。这个操作用于“刚保存完发现上一条质量不好”的场景。

脚本已做过基础校验：

```powershell
python -m py_compile scripts\collect_reverse_demo0.py
python scripts\collect_reverse_demo0.py --help
```

这两个命令可以正常通过；导入时出现的 robosuite / Gym warning 是当前环境已有 warning，不影响脚本参数检查。

### demo 0 反向视频

官方正向 `demo_0` 是 236 帧：

```text
official states (236, 47)
official actions (236, 7)
official num_samples 236
```

已经采集并保存的反向 `demo_0` 是 4022 帧：

```text
demonstration_data_reverse\robosuite_ln_libero_kitchen_tabletop_manipulation_reverse_demo_0_1782831560_2944205\demo.hdf5
```

检查结果：

```text
demos ['demo_0']
states (4022, 47)
actions (4022, 7)
source_demo_name demo_0
source_init_state_index 235
source_goal_state_index 0
```

从核心轨迹维度看，两者是一致的：state 维度都是 47，action 维度都是 7。文件格式不完全一样：官方数据是 LIBERO 训练数据格式，`demo_0` 里有 `obs`、`rewards`、`dones`、`robot_states` 和 `num_samples`；当前反向采集文件是 raw teleop 格式，保存 `states`、`actions`、`source_init_state`、`source_goal_state` 以及 source metadata。已检查：

```text
source_goal_state_vs_official_first_max_abs 0.0
source_init_state_vs_official_last_max_abs 0.0
reverse_first_vs_official_last_max_abs 0.0
```

也就是说反向 demo 的目标首帧、初始化末帧和官方 `demo_0` 一一对应，没有错配。

渲染命令：

```powershell
conda activate libero
cd C:\workspace\LIBERO

$env:MUJOCO_GL = "glfw"

python scripts\render_collected_demo_video.py `
  --demo-file demonstration_data_reverse\robosuite_ln_libero_kitchen_tabletop_manipulation_reverse_demo_0_1782831560_2944205\demo.hdf5 `
  --camera agentview `
  --height 256 `
  --width 256 `
  --fps 20 `
  --stride 1
```

当前已生成视频：

```text
demonstration_data_reverse\robosuite_ln_libero_kitchen_tabletop_manipulation_reverse_demo_0_1782831560_2944205\videos\demo_0_agentview.mp4
```

同时已把官方正向 `demo_0` 也渲染到同一个目录，文件名前缀为 `official_`，避免覆盖反向视频：

```text
demonstration_data_reverse\robosuite_ln_libero_kitchen_tabletop_manipulation_reverse_demo_0_1782831560_2944205\videos\official_demo_0_agentview.mp4
demonstration_data_reverse\robosuite_ln_libero_kitchen_tabletop_manipulation_reverse_demo_0_1782831560_2944205\videos\official_demo_0_agentview_frame0.png
```

官方 `demo_0` 首帧在 `agentview` 下可以看到：桌面左侧是白色杯子，桌面中间偏前是黄白杯子，右侧是打开的微波炉，微波炉门向右侧敞开。

视频格式检查结果：

```text
codec_name=h264
width=256
height=256
pix_fmt=yuv420p
avg_frame_rate=20/1
nb_frames=4022
```

官方正向 `demo_0` 视频格式检查结果：

```text
codec_name=h264
width=256
height=256
pix_fmt=yuv420p
avg_frame_rate=20/1
nb_frames=236
```

### demo 0 时长差距分析

官方正向 `demo_0` 和当前反向 `demo_0` 都是按 `control_freq=20` 采集 / 回放，也就是 20Hz。时长差距不是 FPS 不一致造成的：

```text
official_forward: 236 frames, 11.8 s at 20Hz
reverse_raw: 4022 frames, 201.1 s at 20Hz
frame_ratio_reverse_over_official: 17.04x
```

MuJoCo flattened state 结构是 `[time, qpos(24), qvel(22)]`，其中 robot / gripper qpos 是前 9 维，后面是两个 mug 的 free joint 和 microwave joint。按 robot / gripper qpos 的每步位移统计：

```text
official robot_qpos_step_l2 mean=0.03075 p50=0.03060 p90=0.04662 p95=0.05713 p99=0.06145
reverse  robot_qpos_step_l2 mean=0.00488 p50=0.00036 p90=0.01574 p95=0.02106 p99=0.04558
```

按 robot qvel 统计：

```text
official robot_qvel_l2 mean=0.60540 p50=0.60137 p90=0.94513 p95=1.14711 p99=1.23136
reverse  robot_qvel_l2 mean=0.09877 p50=0.00628 p90=0.33838 p95=0.53366 p99=0.92643
```

也就是说，反向 demo 的大部分时间机械臂在非常慢地移动或停顿；不是单纯“总动作路径一样但采样太密”。反向 demo 的总 robot qpos 路径也更长：

```text
official robot_qpos path length 7.226
reverse  robot_qpos path length 19.605
```

按每步 robot qpos 位移 `> 0.005` 作为有效移动阈值：

```text
official active_frames 232 / 235, active_duration 11.60 s
reverse  active_frames 1072 / 4021, active_duration 53.60 s
```

结论：当前反向轨迹比官方长，主要来自三部分：

- 人工遥操速度明显慢于官方正向 demo。
- 中间有大量停顿、观察、微调和探索段。
- 总机械臂路径更长，说明路径本身也不够直接。

如果直接按帧数比例抽帧，`4022 / 236 ≈ 17`，stride 17 后大约是 237 帧、11.85 秒：

```text
stride 8  -> 503 frames, 25.15 s at 20Hz
stride 10 -> 403 frames, 20.15 s at 20Hz
stride 16 -> 252 frames, 12.60 s at 20Hz
stride 17 -> 237 frames, 11.85 s at 20Hz
```

但不建议把 stride 17 当成默认方案。原因是 raw action 是 20Hz 控制动作，直接抽掉中间 16 个控制步会改变 action 和 state 转移的时间语义；对行为克隆可能还能作为粗糙数据增强，但不再是严格的 20Hz 控制轨迹。

更推荐的顺序是：

1. 重新采集时用目标蒙版减少观察和微调时间，尽量连续移动，少停顿。
2. 适当提高 `--pos-sensitivity`，例如从 `1.5` 提到 `2.0` 或 `2.5`，但不要快到控制不稳或撞击物体。
3. 采集后先做轻量停顿裁剪：删除 robot qpos 几乎不变、物体也几乎不变的长停顿段，而不是机械固定 stride 抽帧。
4. 如果必须统一长度，再考虑基于轨迹进度 / 关键状态的重采样，而不是只按固定步长抽帧。

当前最重要的是下一批 50 条尽量直接、连续地完成恢复；后处理只作为补救，不应代替采集质量。

### 最新最快 demo 0 速度分析

在加入“第一条有效键盘输入后才开始保存”的逻辑后，目前最快的一条反向 `demo_0` 保存到：

```text
demonstration_data_reverse\robosuite_ln_libero_kitchen_tabletop_manipulation_reverse_demo_0_1782896778_1865742\demo.hdf5
```

采集日志：

```text
Skipped idle pre-recording frames: 370
Collected control steps: 2780
```

已和官方正向 `demo_0` 做 Panda 7 个机械臂关节速度 / 加速度对比。这里的速度是 `||arm qvel||`，不包含夹爪和物体速度。

官方 `demo_0`：

```text
frames=236
duration_s=11.8
speed_rad_s mean=0.6036, p50=0.6010, p90=0.9451, p95=1.1471, p99=1.2314, max=1.2551
accel_rad_s2 mean=1.3828, p50=1.2237, p90=2.2215, p95=2.8896, p99=3.9421, max=6.1009
qpos_path_length=7.2057
pause_time_s(speed < 0.05)=0.0
long_pause_count_ge_0_5s=0
```

当前最快反向 `demo_0`：

```text
frames=2780
duration_s=139.0
speed_rad_s mean=0.1036, p50=0.0069, p90=0.3744, p95=0.5453, p99=0.9136, max=1.9306
accel_rad_s2 mean=1.4285, p50=0.0651, p90=5.8245, p95=9.6720, p99=11.4332, max=39.0699
qpos_path_length=14.3901
pause_time_s(speed < 0.05)=92.3
pause_frac=0.6640
long_pause_count_ge_0_5s=65
long_pause_time_s_ge_0_5s=82.2
longest_pause_s=8.75
```

可视化图已生成：

```text
demonstration_data_reverse\robosuite_ln_libero_kitchen_tabletop_manipulation_reverse_demo_0_1782896778_1865742\videos\speed_comparison_official_vs_reverse_demo0.png
demonstration_data_reverse\robosuite_ln_libero_kitchen_tabletop_manipulation_reverse_demo_0_1782896778_1865742\videos\speed_comparison_official_vs_reverse_demo0_summary.txt
```

这张图的上半部分按真实时间显示速度，下半部分把两条轨迹都归一化到 0 到 1 的进度。结论很清楚：官方正向 demo 的速度曲线比较连续、平滑；当前反向 demo 是大量尖峰加长时间接近 0。反向 demo 慢的主要原因仍然是停顿和间歇式微调，而不是最高速度不够。事实上反向 demo 的最高速度 `1.9306 rad/s` 已经高于官方 `1.2551 rad/s`，但中位速度只有 `0.0069 rad/s`，说明大部分时间没有持续运动。

后续采集建议：

1. 优先减少停顿和间歇式调整，让速度曲线更连续。
2. 用目标蒙版提前规划恢复路径，不要在录制中长时间观察。
3. 速度已经能冲到官方水平以上，因此不应只继续增大 `--pos-sensitivity`；如果继续加大，可能只会增加尖峰、过冲和碰撞。
4. 更理想的是连续、稳定地移动，而不是“停很久，然后快速点一下”。

### 新手柄 demo 0 速度分析

使用更新后的 gamepad 控制后，新保存的反向 `demo_0` 位于：

```text
demonstration_data_reverse\robosuite_ln_libero_kitchen_tabletop_manipulation_reverse_demo_0_1782909397_509212\demo.hdf5
```

速度分析图和摘要已生成：

```text
demonstration_data_reverse\robosuite_ln_libero_kitchen_tabletop_manipulation_reverse_demo_0_1782909397_509212\videos\speed_comparison_official_vs_reverse_demo0.png
demonstration_data_reverse\robosuite_ln_libero_kitchen_tabletop_manipulation_reverse_demo_0_1782909397_509212\videos\speed_comparison_official_vs_reverse_demo0_summary.txt
```

官方 `demo_0` 作为对照：

```text
frames=236
duration_s=11.8
speed_rad_s mean=0.6036, p50=0.6010, p75=0.7663, p90=0.9451, p95=1.1471, p99=1.2314, max=1.2551
accel_rad_s2 mean=1.3828, p50=1.2237, p75=1.6629, p90=2.2215, p95=2.8896, p99=3.9421, max=6.1009
qpos_path_length=7.2057
pause_time_s(speed < 0.05)=0.0
```

新 gamepad 反向 `demo_0`：

```text
frames=950
duration_s=47.5
speed_rad_s mean=0.2509, p50=0.1969, p75=0.3589, p90=0.5500, p95=0.7025, p99=0.9174, max=1.9043
accel_rad_s2 mean=0.7271, p50=0.3786, p75=0.8954, p90=1.6329, p95=2.2004, p99=4.6526, max=40.3147
qpos_path_length=12.0182
pause_time_s(speed < 0.05)=10.7
pause_frac=0.2253
long_pause_count_ge_0_5s=8
long_pause_time_s_ge_0_5s=8.6
longest_pause_s=2.2
```

对比之前最快键盘 / 早期手柄数据的 2780 帧、139 秒，新数据已经明显改善：帧数减少到 950，时长减少到 47.5 秒，停顿比例从约 66% 降到约 22.5%。不过它仍然比官方 236 帧、11.8 秒慢约 4 倍，且总 robot qpos 路径 `12.0182` 仍高于官方 `7.2057`。下一步优化重点仍然是减少绕路和停顿，而不是继续提高最高速度；当前最高速度 `1.9043 rad/s` 已经高于官方 `1.2551 rad/s`。

### 转成反向 LIBERO 训练数据格式

raw teleop 文件只有 `states` / `actions` / metadata；LIBERO 训练格式需要重新回放轨迹生成 `obs`、`rewards`、`dones`、`robot_states` 和 `num_samples`。仓库已有 `scripts\create_dataset.py` 可以做这个转换。

为了避免覆盖原本 task 33 的正向官方数据，当前脚本已支持显式输出路径 `--output-file`。转换当前反向 `demo_0`：

```powershell
conda activate libero
cd C:\workspace\LIBERO

$env:MUJOCO_GL = "glfw"
Remove-Item Env:\MUJOCO_EGL_DEVICE_ID -ErrorAction SilentlyContinue

python scripts\create_dataset.py `
  --demo-file demonstration_data_reverse\robosuite_ln_libero_kitchen_tabletop_manipulation_reverse_demo_0_1782831560_2944205\demo.hdf5 `
  --use-camera-obs `
  --output-file demonstration_data_reverse\robosuite_ln_libero_kitchen_tabletop_manipulation_reverse_demo_0_1782831560_2944205\KITCHEN_SCENE6_close_the_microwave_reverse_demo0_libero_format.hdf5
```

转换后的每条 `demo_i` 会包含：

```text
actions
states
robot_states
rewards
dones
obs/agentview_rgb
obs/eye_in_hand_rgb
obs/joint_states
obs/gripper_states
obs/ee_states
obs/ee_pos
obs/ee_ori
attrs["num_samples"]
attrs["model_file"]
attrs["init_state"]
```

注意：`create_dataset.py` 默认会跳过前 5 个控制步，因为原脚本认为 force sensor 初始不稳定。当前反向 `demo_0` 转换后预期样本数会从 4022 变成约 4017。

### 采集 50 条反向数据

已经新增批量反向采集脚本：

```text
scripts\collect_reverse_demonstrations.py
```

它会从官方 `demo_0` 到 `demo_49` 顺序采集 50 条反向数据。每条 episode 开始时加载对应官方 demo 的 `model_file + states[-1]`，人工恢复到接近对应 `states[0]` 后按 `p` 保存。

运行：

```powershell
conda activate libero
cd C:\workspace\LIBERO

$env:MUJOCO_GL = "glfw"
Remove-Item Env:\MUJOCO_EGL_DEVICE_ID -ErrorAction SilentlyContinue

python scripts\collect_reverse_demonstrations.py `
  --device keyboard `
  --robots Panda `
  --bddl-file libero\libero\bddl_files\libero_90\KITCHEN_SCENE6_close_the_microwave.bddl `
  --reference-demo-file data\libero_official\libero_90\KITCHEN_SCENE6_close_the_microwave_demo.hdf5 `
  --demo-index-start 0 `
  --demo-index-end 49 `
  --directory demonstration_data_reverse `
  --camera agentview `
  --controller OSC_POSE `
  --pos-sensitivity 1.5 `
  --rot-sensitivity 1.0 `
  --goal-overlay-alpha 0.3 `
  --viewer-scale 1.5 `
  --start-action-threshold 1e-6 `
  --save-key p `
  --window-title "LIBERO Teleop - Task 33 Reverse"
```

如果使用 PS5 / 游戏手柄采 50 条，把 `--device keyboard` 换成 `--device gamepad`，并加入手柄参数：

```powershell
python scripts\collect_reverse_demonstrations.py `
  --device gamepad `
  --robots Panda `
  --bddl-file libero\libero\bddl_files\libero_90\KITCHEN_SCENE6_close_the_microwave.bddl `
  --reference-demo-file data\libero_official\libero_90\KITCHEN_SCENE6_close_the_microwave_demo.hdf5 `
  --demo-index-start 0 `
  --demo-index-end 49 `
  --directory demonstration_data_reverse `
  --camera agentview `
  --controller OSC_POSE `
  --pos-sensitivity 1.0 `
  --rot-sensitivity 1.0 `
  --goal-overlay-alpha 0.3 `
  --viewer-scale 1.5 `
  --start-action-threshold 1e-6 `
  --gamepad-deadzone 0.08 `
  --gamepad-pos-step 0.01 `
  --gamepad-rot-step 0.01 `
  --gamepad-square-long-press-seconds 0.8 `
  --inter-demo-pause-seconds 1.0 `
  --window-title "LIBERO Teleop - Task 33 Reverse Gamepad"
```

批量脚本会在终端打印进度，例如 `[3/50]`；保存一条后默认等待 `--inter-demo-pause-seconds 1.0` 秒再进入下一条，给操作者一点准备时间。如果你想连续无停顿进入下一条，可以设置 `--inter-demo-pause-seconds 0`。

按键语义：

- 键盘模式下按 `p`：保存当前编号的反向 demo，并进入下一个官方 demo 编号。
- 键盘模式下按 `q`，或手柄模式下长按 `Square` / 按 `Options`：丢弃当前 episode，重新采当前编号。
- 键盘模式下按 `ESC`，或手柄模式下按 `Share`：停止整轮 50 条采集。

如果中途停止，可以用 `--output-dir` 指向已有输出目录，并加 `--resume` 继续。已经存在的 `demo_i` 会跳过：

```powershell
python scripts\collect_reverse_demonstrations.py `
  --output-dir demonstration_data_reverse\<已有的reverse_official_50输出目录> `
  --resume `
  --demo-index-start 0 `
  --demo-index-end 49
```

如果只想补采某个编号，例如 `demo_12`，可以设置：

```powershell
--demo-index-start 12 --demo-index-end 12
```

脚本已做过基础校验：

```powershell
python -m py_compile scripts\collect_reverse_demonstrations.py
python scripts\collect_reverse_demonstrations.py --help
```

### 场景初始化和随机性

Task 33 的 BDDL / scene 生成代码定义了两个杯子和微波炉的初始区域，而不是单个完全固定坐标。`KITCHEN_SCENE6_close_the_microwave.bddl` 中：

- `white_yellow_mug_1` 在 `white_yellow_mug_init_region`，范围是 `(-0.025, -0.025, 0.025, 0.025)`。
- `porcelain_mug_1` 在 `porcelain_mug_init_region`，范围是 `(-0.125, -0.275, -0.075, -0.225)`。
- `microwave_1` 在 `microwave_init_region`，范围是 `(-0.01, 0.34, 0.01, 0.36)`。
- 初始状态包含 `(Open microwave_1)`。

对应的代码在 `libero\libero\benchmark\mu_creation.py` 的 `KitchenScene6`：它定义相同区域，并在 `init_states` 中声明 `porcelain_mug_1`、`white_yellow_mug_1`、`microwave_1` 的 `On` 关系和 `Open microwave_1`。

环境 reset 时，`libero\libero\envs\bddl_base_domain.py` 会根据 BDDL 的 `initial_state` 创建 placement sampler；`MultiRegionRandomSampler` / region sampler 会在区域范围内用 `np.random.uniform` 采样 x、y 和 yaw。因此普通 `env.reset()` 本身有随机性。

但是 LIBERO benchmark 为评测固定了一组初始 states。仓库 README 的示例写到：

```python
init_states = task_suite.get_task_init_states(task_id) # for benchmarking purpose, we fix the a set of initial states
env.set_init_state(init_states[init_state_id])
```

官方 HDF5 里的每条 `demo_i` 也保存了对应的 `init_state`、`model_file` 和 `states`。所以对我们当前反向恢复采集来说，不再依赖 `env.reset()` 的随机采样结果，而是显式使用官方 `demo_i` 的 `model_file + states[-1]` 初始化，并把 `states[0]` 作为恢复目标参考。

LIBERO 论文 / 项目页描述了它有 procedural generation pipeline，可以生成大量任务，并提供高质量人工遥操作 demonstrations；本仓库中关于固定初始状态和具体采样行为的最直接依据是 README、BDDL 和上述环境代码。

### 官方 XML 路径修补

官方 HDF5 的 `model_file` 中保存的是采集官方数据机器上的绝对路径，例如：

```text
/home/yifengz/workspace/libero-dev/chiliocosm/assets/scenes/kitchen_background/visual/kitchen_background_vis.msh
```

如果直接 `env.reset_from_xml_string(model_xml)`，Windows 本机会报类似错误：

```text
ValueError: Error opening file '/home/yifengz/workspace/libero-dev/chiliocosm/assets/scenes/kitchen_background/visual/kitchen_background_vis.msh': No such file or directory
```

`scripts\collect_reverse_demo0.py` 已经在加载官方 XML 前修补这些 asset 路径：

- `robosuite` 资源路径会映射到当前 conda 环境里的 `robosuite` 包。
- `chiliocosm/assets` 资源路径会映射到本仓库的 `libero\libero\assets`。

已验证官方 `demo_0` XML 中 88 个 mesh / texture asset 绝对路径修补后都能在本机找到，并且 MuJoCo 可以直接加载修补后的 XML：

```text
loaded_model_nq 24
loaded_model_nv 22
```

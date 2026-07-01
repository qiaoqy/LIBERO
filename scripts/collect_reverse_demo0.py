import argparse
import datetime
import json
import os
import time
import xml.etree.ElementTree as ET
from glob import glob
from pathlib import Path

import cv2
import h5py
import init_path
import numpy as np
import robosuite as suite
from robosuite import load_controller_config
from robosuite.utils.input_utils import input2action
from robosuite.wrappers import DataCollectionWrapper, VisualizationWrapper

import libero.libero.envs.bddl_utils as BDDLUtils
import libero.libero.utils.utils as libero_utils
from libero.libero.envs import TASK_MAPPING


DEFAULT_RENDER_WINDOW_NAME = "offscreen render"
DEFAULT_SOURCE_DEMO = "demo_0"
DEFAULT_REVERSE_LANGUAGE = "restore the microwave to the initial open state"


class ReverseTeleopRuntime:
    def __init__(self):
        self.stop_requested = False
        self.save_requested = False
        self.undo_requested = False


def set_render_window_title(window_title):
    if not window_title:
        return
    try:
        cv2.setWindowTitle(DEFAULT_RENDER_WINDOW_NAME, window_title)
    except cv2.error:
        pass


def key_matches_char(key, char):
    if isinstance(key, int):
        return key in (ord(char), ord(char.upper()))
    return getattr(key, "char", None) == char


def make_keypress_callback(device, runtime, save_key):
    def on_keypress(key):
        if key == 27:
            runtime.stop_requested = True
            return
        if key_matches_char(key, save_key):
            runtime.save_requested = True
            return
        device.on_press(key)

    return on_keypress


def add_keyboard_callbacks(viewer, device, runtime, save_key):
    keypress_callback = make_keypress_callback(device, runtime, save_key)
    try:
        viewer.add_keypress_callback("any", keypress_callback)
    except TypeError:
        viewer.add_keypress_callback(keypress_callback)

    for method_name, callback in (
        ("add_keyup_callback", device.on_release),
        ("add_keyrepeat_callback", device.on_press),
    ):
        method = getattr(viewer, method_name, None)
        if method is None:
            continue
        try:
            method("any", callback)
        except TypeError:
            method(callback)


class ManualSaveKeyboard:
    def __init__(self, runtime, save_key, pos_sensitivity, rot_sensitivity):
        from robosuite.devices import Keyboard

        class _Keyboard(Keyboard):
            def on_release(self, key):
                if key_matches_char(key, save_key):
                    runtime.save_requested = True
                    self._enabled = False
                    self._reset_internal_state()
                    return
                super().on_release(key)

        self.device = _Keyboard(
            pos_sensitivity=pos_sensitivity,
            rot_sensitivity=rot_sensitivity,
        )


class GamepadDevice:
    def __init__(self, runtime, args):
        try:
            import pygame
        except ImportError as exc:
            raise ImportError("pygame is required for --device gamepad. Install it with: python -m pip install pygame") from exc

        self.pygame = pygame
        pygame.init()
        pygame.joystick.init()
        joystick_count = pygame.joystick.get_count()
        if joystick_count == 0:
            raise RuntimeError("No gamepad detected by pygame. Connect the controller and check Windows game controller settings.")
        if args.gamepad_index >= joystick_count:
            raise ValueError(f"--gamepad-index {args.gamepad_index} is out of range; pygame detected {joystick_count} joystick(s).")

        self.joystick = pygame.joystick.Joystick(args.gamepad_index)
        self.joystick.init()
        self.runtime = runtime
        self.deadzone = args.gamepad_deadzone
        self.pos_step = args.gamepad_pos_step * args.pos_sensitivity
        self.rot_step = args.gamepad_rot_step * args.rot_sensitivity
        self.axis_left_x = args.gamepad_axis_left_x
        self.axis_left_y = args.gamepad_axis_left_y
        self.axis_right_x = args.gamepad_axis_right_x
        self.axis_right_y = args.gamepad_axis_right_y
        self.button_gripper = args.gamepad_button_gripper
        self.button_rotate_modifier = args.gamepad_button_rotate_modifier
        self.button_save_discard = args.gamepad_button_save_discard
        self.button_undo_last = args.gamepad_button_undo_last
        self.button_reset = args.gamepad_button_reset
        self.button_stop = args.gamepad_button_stop
        self.square_long_press_seconds = args.gamepad_square_long_press_seconds
        self.grasp = False
        self.reset = 0
        self.previous_buttons = [0] * self.joystick.get_numbuttons()
        self.button_press_times = {}
        self.square_long_press_active = False

        print(f"Gamepad: {self.joystick.get_name()}")
        print(f"Gamepad axes={self.joystick.get_numaxes()} buttons={self.joystick.get_numbuttons()} hats={self.joystick.get_numhats()}")
        print("Default mapping: left stick xy -> translation xy, right stick y -> z, hold Circle for rotation, Triangle -> gripper, Square short -> save, Square long -> discard/reset, Cross -> undo last saved, Options -> reset, Share -> stop.")

    def start_control(self):
        self.reset = 0
        self.runtime.save_requested = False
        self.runtime.stop_requested = False
        self.runtime.undo_requested = False
        self.square_long_press_active = False
        self.button_press_times = {}

    def on_press(self, key):
        if key_matches_char(key, "q"):
            self.reset = 1

    def on_release(self, key):
        pass

    def _axis(self, axis_index, default=0.0):
        if axis_index < 0 or axis_index >= self.joystick.get_numaxes():
            return default
        value = float(self.joystick.get_axis(axis_index))
        if abs(value) < self.deadzone:
            return 0.0
        return value

    def _trigger(self, axis_index):
        value = self._axis(axis_index, default=-1.0)
        if value < -0.5:
            return max(0.0, min(1.0, (value + 1.0) / 2.0))
        return max(0.0, min(1.0, value))

    def _button(self, button_index):
        if button_index < 0 or button_index >= self.joystick.get_numbuttons():
            return 0
        return int(self.joystick.get_button(button_index))

    def _button_edge(self, button_index):
        current = self._button(button_index)
        previous = self.previous_buttons[button_index] if 0 <= button_index < len(self.previous_buttons) else 0
        return current == 1 and previous == 0

    def _button_release_edge(self, button_index):
        current = self._button(button_index)
        previous = self.previous_buttons[button_index] if 0 <= button_index < len(self.previous_buttons) else 0
        return current == 0 and previous == 1

    @staticmethod
    def _limit_unit_vector(vector):
        norm = np.linalg.norm(vector)
        if norm > 1.0:
            return vector / norm
        return vector

    def _rumble(self, count):
        if not hasattr(self.joystick, "rumble"):
            return
        for index in range(count):
            try:
                self.joystick.rumble(0.0, 0.75, 120)
            except Exception:
                return
            if index < count - 1:
                time.sleep(0.18)

    def _start_rumble(self):
        if not hasattr(self.joystick, "rumble"):
            return
        try:
            self.joystick.rumble(0.0, 0.75, 0)
        except Exception:
            return

    def _stop_rumble(self):
        if not hasattr(self.joystick, "stop_rumble"):
            return
        try:
            self.joystick.stop_rumble()
        except Exception:
            return

    def close(self):
        self._stop_rumble()

    def get_controller_state(self):
        self.pygame.event.pump()

        if self._button_edge(self.button_gripper):
            self.grasp = not self.grasp
        if self._button_edge(self.button_save_discard):
            self.button_press_times[self.button_save_discard] = time.time()
            self.square_long_press_active = False
        if self._button(self.button_save_discard) and self.button_save_discard in self.button_press_times:
            held_seconds = time.time() - self.button_press_times[self.button_save_discard]
            if held_seconds >= self.square_long_press_seconds and not self.square_long_press_active:
                self.square_long_press_active = True
                self._start_rumble()
        if self._button_release_edge(self.button_save_discard):
            press_time = self.button_press_times.pop(self.button_save_discard, time.time())
            if self.square_long_press_active or time.time() - press_time >= self.square_long_press_seconds:
                self._stop_rumble()
                self.square_long_press_active = False
                self.reset = 1
            else:
                self.runtime.save_requested = True
                self._rumble(1)
        if self._button_edge(self.button_undo_last):
            self.runtime.undo_requested = True
        if self._button_edge(self.button_reset):
            self.reset = 1
        if self._button_edge(self.button_stop):
            self.runtime.stop_requested = True

        left_x = self._axis(self.axis_left_x)
        left_y = self._axis(self.axis_left_y)
        right_x = self._axis(self.axis_right_x)
        right_y = self._axis(self.axis_right_y)
        rotate_mode = bool(self._button(self.button_rotate_modifier))

        if rotate_mode:
            dpos_axis = np.zeros(3)
            rotation_axis = self._limit_unit_vector(
                np.array(
                    [
                        -left_y,
                        -right_y + left_x,
                        right_x,
                    ],
                    dtype=float,
                )
            )
        else:
            z_axis = -right_y
            dpos_axis = self._limit_unit_vector(np.array([left_y, left_x, z_axis], dtype=float))
            rotation_axis = np.zeros(3)

        dpos = dpos_axis * self.pos_step
        raw_drotation = rotation_axis * self.rot_step
        rotation = np.eye(3)

        self.previous_buttons = [self._button(index) for index in range(self.joystick.get_numbuttons())]
        reset = self.reset
        self.reset = 0
        return dict(
            dpos=dpos,
            rotation=rotation,
            raw_drotation=raw_drotation,
            grasp=int(self.grasp),
            reset=reset,
        )


def add_gamepad_args(parser):
    parser.add_argument("--gamepad-index", type=int, default=0)
    parser.add_argument("--gamepad-deadzone", type=float, default=0.08)
    parser.add_argument("--gamepad-pos-step", type=float, default=0.01)
    parser.add_argument("--gamepad-rot-step", type=float, default=0.01)
    parser.add_argument("--gamepad-axis-left-x", type=int, default=0)
    parser.add_argument("--gamepad-axis-left-y", type=int, default=1)
    parser.add_argument("--gamepad-axis-right-x", type=int, default=2)
    parser.add_argument("--gamepad-axis-right-y", type=int, default=3)
    parser.add_argument("--gamepad-button-gripper", type=int, default=3)
    parser.add_argument("--gamepad-button-rotate-modifier", type=int, default=1)
    parser.add_argument("--gamepad-button-save-discard", type=int, default=2)
    parser.add_argument("--gamepad-button-undo-last", type=int, default=0)
    parser.add_argument("--gamepad-button-reset", type=int, default=6)
    parser.add_argument("--gamepad-button-stop", type=int, default=4)
    parser.add_argument("--gamepad-square-long-press-seconds", type=float, default=0.8)


def create_input_device(args, runtime):
    if args.device == "keyboard":
        keyboard = ManualSaveKeyboard(
            runtime=runtime,
            save_key=args.save_key,
            pos_sensitivity=args.pos_sensitivity,
            rot_sensitivity=args.rot_sensitivity,
        )
        return keyboard.device
    if args.device == "gamepad":
        return GamepadDevice(runtime, args)
    raise Exception("Invalid device choice: choose 'keyboard' or 'gamepad'.")


def get_source_demo(reference_demo_file, source_demo_name):
    with h5py.File(reference_demo_file, "r") as hdf5_file:
        if "data" not in hdf5_file:
            raise ValueError(f"{reference_demo_file} does not contain a data group")
        if source_demo_name not in hdf5_file["data"]:
            available = sorted(hdf5_file["data"].keys())
            raise ValueError(
                f"{source_demo_name} not found in {reference_demo_file}; available demos: {available[:5]}..."
            )

        demo_group = hdf5_file[f"data/{source_demo_name}"]
        model_xml = demo_group.attrs["model_file"]
        if isinstance(model_xml, bytes):
            model_xml = model_xml.decode("utf-8")
        states = demo_group["states"][()]
        actions = demo_group["actions"][()]

    if len(states) == 0:
        raise ValueError(f"{source_demo_name} has no states")
    return {
        "source_demo_name": source_demo_name,
        "model_xml": model_xml,
        "init_state": np.array(states[-1]),
        "goal_state": np.array(states[0]),
        "source_init_state_index": len(states) - 1,
        "source_goal_state_index": 0,
        "source_state_shape": states.shape,
        "source_action_shape": actions.shape,
    }


def rewrite_libero_asset_path(asset_path):
    normalized_path = asset_path.replace("\\", "/")
    assets_marker = "/chiliocosm/assets/"
    if assets_marker in normalized_path:
        suffix = normalized_path.split(assets_marker, 1)[1]
        repo_root = Path(__file__).resolve().parents[1]
        return (repo_root / "libero" / "libero" / "assets" / Path(*suffix.split("/"))).as_posix()
    return asset_path


def postprocess_official_model_xml(xml_str):
    xml_str = libero_utils.postprocess_model_xml(xml_str, {})
    root = ET.fromstring(xml_str)
    asset = root.find("asset")
    if asset is None:
        return xml_str

    for elem in list(asset.findall("mesh")) + list(asset.findall("texture")):
        asset_file = elem.get("file")
        if asset_file is None:
            continue
        elem.set("file", rewrite_libero_asset_path(asset_file))

    return ET.tostring(root, encoding="utf8").decode("utf8")


def set_viewer_camera(env, camera_name):
    viewer = getattr(env, "viewer", None)
    if viewer is None:
        return
    if hasattr(viewer, "sim"):
        viewer.sim = env.sim
    if not camera_name:
        return
    try:
        camera_id = env.sim.model.camera_name2id(camera_name)
        if hasattr(viewer, "set_camera"):
            viewer.set_camera(camera_id)
        elif hasattr(viewer, "camera_name"):
            viewer.camera_name = camera_name
    except Exception:
        if hasattr(viewer, "camera_name"):
            viewer.camera_name = camera_name


def set_viewer_scale(env, viewer_scale):
    viewer = getattr(env, "viewer", None)
    if viewer is None or viewer_scale is None:
        return
    if viewer_scale <= 0:
        raise ValueError("--viewer-scale must be positive")
    if not hasattr(viewer, "_libero_base_width"):
        viewer._libero_base_width = getattr(viewer, "width", 1280)
        viewer._libero_base_height = getattr(viewer, "height", 800)
    if hasattr(viewer, "width"):
        viewer.width = int(round(viewer._libero_base_width * viewer_scale))
    if hasattr(viewer, "height"):
        viewer.height = int(round(viewer._libero_base_height * viewer_scale))
    print(f"OpenCV viewer size: {getattr(viewer, 'width', 1280)}x{getattr(viewer, 'height', 800)} (scale={viewer_scale})")


def resize_render_window(env):
    viewer = getattr(env, "viewer", None)
    width = int(getattr(viewer, "width", 1280)) if viewer is not None else 1280
    height = int(getattr(viewer, "height", 800)) if viewer is not None else 800
    try:
        cv2.namedWindow(DEFAULT_RENDER_WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(DEFAULT_RENDER_WINDOW_NAME, width, height)
    except cv2.error:
        pass


def get_viewer_frame(env):
    viewer = env.viewer
    camera_name = getattr(viewer, "camera_name", None)
    width = getattr(viewer, "width", 1280)
    height = getattr(viewer, "height", 800)
    frame = env.sim.render(camera_name=camera_name, height=height, width=width)[..., ::-1]
    return np.flip(frame, axis=0)


def render_goal_overlay_frame(env, source_demo, camera_name):
    set_viewer_camera(env, camera_name)
    env.sim.set_state_from_flattened(source_demo["goal_state"])
    env.sim.forward()
    return get_viewer_frame(env)


def render_teleop_frame(env, goal_overlay_frame, overlay_alpha, window_title):
    if goal_overlay_frame is None or overlay_alpha <= 0:
        resize_render_window(env)
        env.render()
        resize_render_window(env)
        set_render_window_title(window_title)
        return

    current_frame = get_viewer_frame(env)
    if goal_overlay_frame.shape[:2] != current_frame.shape[:2]:
        goal_overlay_frame = cv2.resize(
            goal_overlay_frame,
            (current_frame.shape[1], current_frame.shape[0]),
            interpolation=cv2.INTER_AREA,
        )
    blended_frame = cv2.addWeighted(
        current_frame,
        1.0 - overlay_alpha,
        goal_overlay_frame,
        overlay_alpha,
        0,
    )
    resize_render_window(env)
    cv2.imshow(DEFAULT_RENDER_WINDOW_NAME, blended_frame)
    key = cv2.waitKey(1)
    keypress_callback = getattr(env.viewer, "keypress_callback", None)
    if keypress_callback:
        keypress_callback(key)
    set_render_window_title(window_title)


def is_recording_start_action(action, grasp, previous_grasp, start_action_threshold):
    pose_action = action[:-1]
    pose_started = np.linalg.norm(pose_action) > start_action_threshold
    gripper_started = previous_grasp is not None and grasp != previous_grasp
    return pose_started or gripper_started


def reset_to_source_final_state(env, source_demo, camera_name=None, overlay_alpha=0.3, use_goal_overlay=True, viewer_scale=1.0):
    reset_success = False
    while not reset_success:
        try:
            env.reset()
            reset_success = True
        except Exception:
            continue

    model_xml = postprocess_official_model_xml(source_demo["model_xml"])
    env.reset_from_xml_string(model_xml)
    env.sim.reset()
    set_viewer_camera(env, camera_name)
    set_viewer_scale(env, viewer_scale)

    goal_overlay_frame = None
    if use_goal_overlay and overlay_alpha > 0:
        goal_overlay_frame = render_goal_overlay_frame(env, source_demo, camera_name)

    env.sim.set_state_from_flattened(source_demo["init_state"])
    env.sim.forward()
    env._start_new_episode()
    return goal_overlay_frame


def collect_reverse_human_trajectory(
    env,
    device,
    arm,
    env_configuration,
    source_demo,
    remove_directory,
    runtime,
    window_title,
    save_key,
    camera_name=None,
    goal_overlay_alpha=0.3,
    use_goal_overlay=True,
    start_action_threshold=1e-6,
    viewer_scale=1.0,
):
    runtime.stop_requested = False
    runtime.save_requested = False
    runtime.undo_requested = False

    goal_overlay_frame = reset_to_source_final_state(
        env,
        source_demo,
        camera_name=camera_name,
        overlay_alpha=goal_overlay_alpha,
        use_goal_overlay=use_goal_overlay,
        viewer_scale=viewer_scale,
    )
    render_teleop_frame(env, goal_overlay_frame, goal_overlay_alpha, window_title)

    print(f"Loaded {source_demo['source_demo_name']} final state as reverse initial state.")
    print(f"Use keyboard teleop to restore the scene. Press '{save_key}' to save, q to discard, ESC to quit.")
    if goal_overlay_frame is not None:
        print(f"Showing official first-frame goal overlay at alpha={goal_overlay_alpha} using camera {camera_name}.")

    device.start_control()
    saving = False
    count = 0
    idle_count = 0
    recording_started = False
    previous_grasp = -1

    while True:
        if runtime.stop_requested:
            break

        if runtime.undo_requested:
            break

        if runtime.save_requested:
            if getattr(env, "has_interaction", False):
                saving = True
                break
            print("No interaction has been recorded yet; move the robot before saving.")
            runtime.save_requested = False

        active_robot = env.robots[0] if env_configuration == "bimanual" else env.robots[arm == "left"]
        action, grasp = input2action(
            device=device,
            robot=active_robot,
            active_arm=arm,
            env_configuration=env_configuration,
        )

        if action is None:
            print("Discarding current reverse episode.")
            break

        if runtime.stop_requested or runtime.undo_requested:
            break

        if runtime.save_requested:
            if getattr(env, "has_interaction", False):
                saving = True
                break
            print("No interaction has been recorded yet; move the robot before saving.")
            runtime.save_requested = False

        if not recording_started:
            if not is_recording_start_action(action, grasp, previous_grasp, start_action_threshold):
                render_teleop_frame(env, goal_overlay_frame, goal_overlay_alpha, window_title)
                previous_grasp = grasp
                idle_count += 1
                continue
            recording_started = True
            print("Started recording at the first effective keyboard input.")

        count += 1
        env.step(action)
        render_teleop_frame(env, goal_overlay_frame, goal_overlay_alpha, window_title)
        previous_grasp = grasp

    print(f"Skipped idle pre-recording frames: {idle_count}")
    print(f"Collected control steps: {count}")
    close_device = getattr(device, "close", None)
    if close_device is not None:
        close_device()
    if not saving and getattr(env, "ep_directory", None):
        remove_directory.append(os.path.basename(env.ep_directory))
    env.close()
    undo_requested = runtime.undo_requested
    runtime.undo_requested = False
    return saving, runtime.stop_requested, undo_requested


def gather_reverse_demonstrations_as_hdf5(directory, out_dir, env_info, args, source_demo, problem_info, remove_directory):
    hdf5_path = os.path.join(out_dir, "demo.hdf5")
    with h5py.File(hdf5_path, "w") as hdf5_file:
        grp = hdf5_file.create_group("data")
        num_eps = 0
        env_name = None

        for ep_directory in os.listdir(directory):
            if ep_directory in remove_directory:
                continue

            state_paths = os.path.join(directory, ep_directory, "state_*.npz")
            states = []
            actions = []

            for state_file in sorted(glob(state_paths)):
                episode = np.load(state_file, allow_pickle=True)
                env_name = str(episode["env"])
                states.extend(episode["states"])
                for action_info in episode["action_infos"]:
                    actions.append(action_info["actions"])

            if len(states) == 0:
                continue

            del states[-1]
            assert len(states) == len(actions)

            ep_data_grp = grp.create_group(f"demo_{num_eps}")
            xml_path = os.path.join(directory, ep_directory, "model.xml")
            with open(xml_path, "r") as xml_file:
                xml_str = xml_file.read()
            ep_data_grp.attrs["model_file"] = xml_str
            ep_data_grp.attrs["source_demo_file"] = os.path.abspath(args.reference_demo_file)
            ep_data_grp.attrs["source_demo_name"] = source_demo["source_demo_name"]
            ep_data_grp.attrs["source_init_state_index"] = source_demo["source_init_state_index"]
            ep_data_grp.attrs["source_goal_state_index"] = source_demo["source_goal_state_index"]
            ep_data_grp.attrs["reverse_task_language"] = args.reverse_task_language
            ep_data_grp.create_dataset("states", data=np.array(states))
            ep_data_grp.create_dataset("actions", data=np.array(actions))
            ep_data_grp.create_dataset("source_init_state", data=source_demo["init_state"])
            ep_data_grp.create_dataset("source_goal_state", data=source_demo["goal_state"])
            num_eps += 1

        now = datetime.datetime.now()
        grp.attrs["date"] = f"{now.month}-{now.day}-{now.year}"
        grp.attrs["time"] = f"{now.hour}:{now.minute}:{now.second}"
        grp.attrs["repository_version"] = suite.__version__
        grp.attrs["env"] = env_name
        grp.attrs["env_info"] = env_info
        grp.attrs["problem_info"] = json.dumps(problem_info)
        grp.attrs["bddl_file_name"] = args.bddl_file
        with open(args.bddl_file, "r", encoding="utf-8") as bddl_file:
            grp.attrs["bddl_file_content"] = bddl_file.read()
        grp.attrs["source_demo_file"] = os.path.abspath(args.reference_demo_file)
        grp.attrs["source_demo_name"] = source_demo["source_demo_name"]
        grp.attrs["source_num_demos_expected"] = 50
        grp.attrs["reverse_task_language"] = args.reverse_task_language

    return hdf5_path, num_eps


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=str, default="demonstration_data_reverse")
    parser.add_argument("--robots", nargs="+", type=str, default=["Panda"])
    parser.add_argument("--config", type=str, default="single-arm-opposed")
    parser.add_argument("--arm", type=str, default="right")
    parser.add_argument("--camera", type=str, default="agentview")
    parser.add_argument("--controller", type=str, default="OSC_POSE")
    parser.add_argument("--device", type=str, default="keyboard")
    parser.add_argument("--pos-sensitivity", type=float, default=1.5)
    parser.add_argument("--rot-sensitivity", type=float, default=1.0)
    parser.add_argument(
        "--bddl-file",
        type=str,
        default="libero/libero/bddl_files/libero_90/KITCHEN_SCENE6_close_the_microwave.bddl",
    )
    parser.add_argument(
        "--reference-demo-file",
        type=str,
        default="data/libero_official/libero_90/KITCHEN_SCENE6_close_the_microwave_demo.hdf5",
    )
    parser.add_argument("--source-demo-name", type=str, default=DEFAULT_SOURCE_DEMO)
    parser.add_argument("--save-key", type=str, default="p")
    parser.add_argument("--window-title", type=str, default="LIBERO Teleop - Task 33 Reverse Demo 0")
    parser.add_argument("--reverse-task-language", type=str, default=DEFAULT_REVERSE_LANGUAGE)
    parser.add_argument("--goal-overlay-alpha", type=float, default=0.3)
    parser.add_argument("--viewer-scale", type=float, default=1.5)
    parser.add_argument("--disable-goal-overlay", action="store_true")
    parser.add_argument(
        "--start-action-threshold",
        type=float,
        default=1e-6,
        help="Pose-action norm threshold used to start recording and skip idle pre-motion frames.",
    )
    add_gamepad_args(parser)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.device not in ("keyboard", "gamepad"):
        raise ValueError("collect_reverse_demo0.py currently supports --device keyboard or --device gamepad")
    if len(args.save_key) != 1:
        raise ValueError("--save-key must be a single character")

    assert os.path.exists(args.bddl_file), args.bddl_file
    assert os.path.exists(args.reference_demo_file), args.reference_demo_file

    source_demo = get_source_demo(args.reference_demo_file, args.source_demo_name)
    print(f"Reference file: {args.reference_demo_file}")
    print(f"Source demo: {source_demo['source_demo_name']}")
    print(f"Source states shape: {source_demo['source_state_shape']}")
    print(f"Source actions shape: {source_demo['source_action_shape']}")
    print(f"Reverse initial state index: {source_demo['source_init_state_index']}")
    print("Reverse goal state index: 0")

    controller_config = load_controller_config(default_controller=args.controller)
    config = {
        "robots": args.robots,
        "controller_configs": controller_config,
    }

    problem_info = BDDLUtils.get_problem_info(args.bddl_file)
    problem_name = problem_info["problem_name"]
    domain_name = problem_info["domain_name"]
    if "TwoArm" in problem_name:
        config["env_configuration"] = args.config

    env_info = json.dumps(config)

    timestamp = str(time.time()).replace(".", "_")
    tmp_directory = os.path.join(
        args.directory,
        "tmp",
        f"{problem_name}_reverse_{args.source_demo_name}_{timestamp}",
    )

    runtime = ReverseTeleopRuntime()
    device = create_input_device(args, runtime)

    t1, t2 = str(time.time()).split(".")
    new_dir = os.path.join(
        args.directory,
        f"{domain_name}_ln_{problem_name}_reverse_{args.source_demo_name}_{t1}_{t2}",
    )
    os.makedirs(new_dir)

    remove_directory = []
    while True:
        env = TASK_MAPPING[problem_name](
            bddl_file_name=args.bddl_file,
            **config,
            has_renderer=True,
            has_offscreen_renderer=False,
            render_camera=args.camera,
            ignore_done=True,
            use_camera_obs=False,
            reward_shaping=True,
            control_freq=20,
        )
        env = VisualizationWrapper(env)
        env = DataCollectionWrapper(env, tmp_directory)
        add_keyboard_callbacks(env.viewer, device, runtime, args.save_key)

        saving, stop_requested, undo_requested = collect_reverse_human_trajectory(
            env=env,
            device=device,
            arm=args.arm,
            env_configuration=args.config,
            source_demo=source_demo,
            remove_directory=remove_directory,
            runtime=runtime,
            window_title=args.window_title,
            save_key=args.save_key,
            camera_name=args.camera,
            goal_overlay_alpha=args.goal_overlay_alpha,
            use_goal_overlay=not args.disable_goal_overlay,
            start_action_threshold=args.start_action_threshold,
            viewer_scale=args.viewer_scale,
        )

        if stop_requested:
            print("Stopping reverse collection and closing the render window.")
            break
        if undo_requested:
            print(f"No previous saved demo exists in single-demo mode; resetting scene and retrying {args.source_demo_name}.")
            continue
        if saving:
            hdf5_path, num_eps = gather_reverse_demonstrations_as_hdf5(
                tmp_directory,
                new_dir,
                env_info,
                args,
                source_demo,
                problem_info,
                remove_directory,
            )
            print(f"Saved {num_eps} reverse demo to {hdf5_path}")
            break

        print(f"Discarded {args.source_demo_name}; resetting scene and retrying the same source demo.")
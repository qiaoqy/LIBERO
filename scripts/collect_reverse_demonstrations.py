import argparse
import datetime
import json
import os
import time
from glob import glob
from pathlib import Path

import h5py
import init_path
import numpy as np
import robosuite as suite
from robosuite import load_controller_config
from robosuite.wrappers import DataCollectionWrapper, VisualizationWrapper

import libero.libero.envs.bddl_utils as BDDLUtils
from libero.libero.envs import TASK_MAPPING

from collect_reverse_demo0 import (
    DEFAULT_REVERSE_LANGUAGE,
    ReverseTeleopRuntime,
    SUPPORTED_DEVICES,
    add_gamepad_args,
    add_keyboard_callbacks,
    collect_reverse_human_trajectory,
    create_input_device,
    get_source_demo,
)


def demo_name_from_index(index):
    return f"demo_{index}"


def make_env(args, config, problem_name, tmp_directory, device, runtime, window_title):
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
    return env


def initialize_output_hdf5(hdf5_path, env_info, problem_info, args):
    hdf5_path.parent.mkdir(parents=True, exist_ok=True)
    if hdf5_path.exists() and not args.resume:
        raise FileExistsError(f"{hdf5_path} already exists. Pass --resume to continue writing into it.")

    if hdf5_path.exists():
        return

    with h5py.File(hdf5_path, "w") as hdf5_file:
        grp = hdf5_file.create_group("data")
        now = datetime.datetime.now()
        grp.attrs["date"] = f"{now.month}-{now.day}-{now.year}"
        grp.attrs["time"] = f"{now.hour}:{now.minute}:{now.second}"
        grp.attrs["repository_version"] = suite.__version__
        grp.attrs["env_info"] = env_info
        grp.attrs["problem_info"] = json.dumps(problem_info)
        grp.attrs["bddl_file_name"] = args.bddl_file
        with open(args.bddl_file, "r", encoding="utf-8") as bddl_file:
            grp.attrs["bddl_file_content"] = bddl_file.read()
        grp.attrs["source_demo_file"] = os.path.abspath(args.reference_demo_file)
        grp.attrs["source_demo_start"] = args.demo_index_start
        grp.attrs["source_demo_end"] = args.demo_index_end
        grp.attrs["source_num_demos_expected"] = 50
        grp.attrs["reverse_task_language"] = args.reverse_task_language


def read_collected_episode(tmp_directory, remove_directory):
    env_name = None
    for ep_directory in sorted(os.listdir(tmp_directory)):
        if ep_directory in remove_directory:
            continue

        state_paths = os.path.join(tmp_directory, ep_directory, "state_*.npz")
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
        if len(states) != len(actions):
            raise ValueError(f"Collected state/action length mismatch: {len(states)} states vs {len(actions)} actions")

        xml_path = os.path.join(tmp_directory, ep_directory, "model.xml")
        with open(xml_path, "r") as xml_file:
            model_xml = xml_file.read()
        return env_name, model_xml, np.array(states), np.array(actions)

    raise ValueError(f"No saved episode found in {tmp_directory}")


def append_reverse_demo(hdf5_path, target_demo_name, tmp_directory, remove_directory, source_demo, args):
    env_name, model_xml, states, actions = read_collected_episode(tmp_directory, remove_directory)
    with h5py.File(hdf5_path, "a") as hdf5_file:
        grp = hdf5_file["data"]
        if target_demo_name in grp:
            if args.resume:
                del grp[target_demo_name]
            else:
                raise ValueError(f"{target_demo_name} already exists in {hdf5_path}")

        ep_data_grp = grp.create_group(target_demo_name)
        ep_data_grp.attrs["model_file"] = model_xml
        ep_data_grp.attrs["source_demo_file"] = os.path.abspath(args.reference_demo_file)
        ep_data_grp.attrs["source_demo_name"] = source_demo["source_demo_name"]
        ep_data_grp.attrs["source_init_state_index"] = source_demo["source_init_state_index"]
        ep_data_grp.attrs["source_goal_state_index"] = source_demo["source_goal_state_index"]
        ep_data_grp.attrs["reverse_task_language"] = args.reverse_task_language
        ep_data_grp.create_dataset("states", data=states)
        ep_data_grp.create_dataset("actions", data=actions)
        ep_data_grp.create_dataset("source_init_state", data=source_demo["init_state"])
        ep_data_grp.create_dataset("source_goal_state", data=source_demo["goal_state"])
        grp.attrs["env"] = env_name
        recompute_dataset_counts(grp)
    return states.shape[0]


def recompute_dataset_counts(grp):
    grp.attrs["total"] = sum(grp[name]["actions"].shape[0] for name in grp.keys())
    grp.attrs["num_demos"] = len(grp.keys())


def delete_saved_demo(hdf5_path, demo_name):
    with h5py.File(hdf5_path, "a") as hdf5_file:
        grp = hdf5_file["data"]
        if demo_name not in grp:
            return False
        del grp[demo_name]
        recompute_dataset_counts(grp)
    return True


def find_previous_saved_demo_index(hdf5_path, current_demo_index, min_demo_index):
    with h5py.File(hdf5_path, "r") as hdf5_file:
        saved_demo_names = set(hdf5_file["data"].keys())
    for demo_index in range(current_demo_index - 1, min_demo_index - 1, -1):
        if demo_name_from_index(demo_index) in saved_demo_names:
            return demo_index
    return None


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=str, default="demonstration_data_reverse")
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--robots", nargs="+", type=str, default=["Panda"])
    parser.add_argument("--config", type=str, default="single-arm-opposed")
    parser.add_argument("--arm", type=str, default="right")
    parser.add_argument("--camera", type=str, default="agentview")
    parser.add_argument("--controller", type=str, default="OSC_POSE")
    parser.add_argument("--device", type=str, default="auto", choices=SUPPORTED_DEVICES)
    parser.add_argument("--pos-sensitivity", type=float, default=1.5)
    parser.add_argument("--rot-sensitivity", type=float, default=1.0)
    parser.add_argument("--demo-index-start", type=int, default=0)
    parser.add_argument("--demo-index-end", type=int, default=49)
    parser.add_argument("--inter-demo-pause-seconds", type=float, default=1.0)
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
    parser.add_argument("--save-key", type=str, default="p")
    parser.add_argument("--window-title", type=str, default="LIBERO Teleop - Task 33 Reverse")
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
    if args.device not in SUPPORTED_DEVICES:
        raise ValueError(f"collect_reverse_demonstrations.py currently supports --device {SUPPORTED_DEVICES}")
    if len(args.save_key) != 1:
        raise ValueError("--save-key must be a single character")
    if args.demo_index_start > args.demo_index_end:
        raise ValueError("--demo-index-start must be <= --demo-index-end")

    assert os.path.exists(args.bddl_file), args.bddl_file
    assert os.path.exists(args.reference_demo_file), args.reference_demo_file

    controller_config = load_controller_config(default_controller=args.controller)
    config = {
        "robots": args.robots,
        "controller_configs": controller_config,
    }
    env_info = json.dumps(config)

    problem_info = BDDLUtils.get_problem_info(args.bddl_file)
    problem_name = problem_info["problem_name"]
    domain_name = problem_info["domain_name"]
    if "TwoArm" in problem_name:
        config["env_configuration"] = args.config

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        t1, t2 = str(time.time()).split(".")
        output_dir = Path(args.directory) / f"{domain_name}_ln_{problem_name}_reverse_official_50_{t1}_{t2}"
    hdf5_path = output_dir / "demo.hdf5"
    initialize_output_hdf5(hdf5_path, env_info, problem_info, args)

    runtime = ReverseTeleopRuntime()
    device = create_input_device(args, runtime)

    total_to_visit = args.demo_index_end - args.demo_index_start + 1
    demo_index = args.demo_index_start
    while demo_index <= args.demo_index_end:
        visit_offset = demo_index - args.demo_index_start + 1
        source_demo_name = demo_name_from_index(demo_index)
        target_demo_name = source_demo_name

        with h5py.File(hdf5_path, "r") as hdf5_file:
            already_collected = target_demo_name in hdf5_file["data"]
        if already_collected and args.resume:
            print(f"Skipping existing {target_demo_name} in {hdf5_path}")
            continue
        if already_collected:
            raise ValueError(f"{target_demo_name} already exists in {hdf5_path}; pass --resume to skip it")

        source_demo = get_source_demo(args.reference_demo_file, source_demo_name)
        print("")
        print(f"Collecting reverse {target_demo_name} from official {source_demo_name} [{visit_offset}/{total_to_visit}]")
        print(f"Source states shape: {source_demo['source_state_shape']}")
        print(f"Reverse initial state index: {source_demo['source_init_state_index']}")
        print("Reverse goal state index: 0")

        while True:
            timestamp = str(time.time()).replace(".", "_")
            tmp_directory = os.path.join(
                args.directory,
                "tmp",
                f"{problem_name}_reverse_{source_demo_name}_{timestamp}",
            )
            env = make_env(
                args,
                config,
                problem_name,
                tmp_directory,
                device,
                runtime,
                f"{args.window_title} - {source_demo_name}",
            )
            remove_directory = []
            saving, stop_requested, undo_requested = collect_reverse_human_trajectory(
                env=env,
                device=device,
                arm=args.arm,
                env_configuration=args.config,
                source_demo=source_demo,
                remove_directory=remove_directory,
                runtime=runtime,
                window_title=f"{args.window_title} - {source_demo_name}",
                save_key=args.save_key,
                camera_name=args.camera,
                goal_overlay_alpha=args.goal_overlay_alpha,
                use_goal_overlay=not args.disable_goal_overlay,
                start_action_threshold=args.start_action_threshold,
                viewer_scale=args.viewer_scale,
            )

            if stop_requested:
                print("Stopping reverse collection.")
                raise SystemExit(0)
            if undo_requested:
                previous_demo_index = find_previous_saved_demo_index(
                    hdf5_path,
                    demo_index,
                    args.demo_index_start,
                )
                if previous_demo_index is None:
                    print("No previous saved demo to undo; retrying the current source demo.")
                    continue
                previous_demo_name = demo_name_from_index(previous_demo_index)
                if delete_saved_demo(hdf5_path, previous_demo_name):
                    print(f"Deleted previously saved {previous_demo_name}; returning to recollect it.")
                    demo_index = previous_demo_index
                    break
                print(f"Could not delete {previous_demo_name}; retrying current source demo.")
                continue
            if saving:
                frame_count = append_reverse_demo(
                    hdf5_path,
                    target_demo_name,
                    tmp_directory,
                    remove_directory,
                    source_demo,
                    args,
                )
                print(f"Saved {target_demo_name} to {hdf5_path} ({frame_count} steps)")
                if demo_index < args.demo_index_end and args.inter_demo_pause_seconds > 0:
                    print(f"Preparing next source demo in {args.inter_demo_pause_seconds:.1f}s...")
                    time.sleep(args.inter_demo_pause_seconds)
                demo_index += 1
                break

            print(f"Discarded {target_demo_name}; retrying the same source demo.")

    print(f"Finished reverse collection: {hdf5_path}")
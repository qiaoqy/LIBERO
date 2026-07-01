import argparse
import json
import shutil
import subprocess
from pathlib import Path

import h5py
import numpy as np

import init_path
import libero.libero.utils.utils as libero_utils
from libero.libero.envs import TASK_MAPPING
from collect_reverse_demo0 import postprocess_official_model_xml


def render_frame(env, camera_name, height, width):
    frame = env.sim.render(camera_name=camera_name, height=height, width=width)
    frame = np.flip(frame, axis=0)
    return frame[..., ::-1]


def get_ffmpeg_path(ffmpeg_path=None):
    if ffmpeg_path:
        return ffmpeg_path
    resolved_path = shutil.which("ffmpeg")
    if resolved_path:
        return resolved_path
    raise RuntimeError("ffmpeg was not found on PATH. Install ffmpeg or pass --ffmpeg-path.")


def make_h264_writer(output_path, width, height, fps, ffmpeg_path):
    if width % 2 != 0 or height % 2 != 0:
        raise ValueError("H.264 yuv420p output requires even --width and --height values.")

    command = [
        ffmpeg_path,
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    return subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def render_demo(env, demo_group, output_path, camera_name, height, width, fps, stride, ffmpeg_path):
    model_xml = demo_group.attrs["model_file"]
    model_xml = postprocess_official_model_xml(model_xml)
    states = demo_group["states"][()]

    env.reset()
    env.reset_from_xml_string(model_xml)
    env.sim.reset()

    writer = make_h264_writer(output_path, width, height, fps, ffmpeg_path)

    frame_count = 0
    try:
        for state in states[::stride]:
            env.sim.set_state_from_flattened(state)
            env.sim.forward()
            writer.stdin.write(render_frame(env, camera_name, height, width).tobytes())
            frame_count += 1
    finally:
        if writer.stdin:
            writer.stdin.close()

    stderr = writer.stderr.read().decode("utf-8", errors="replace") if writer.stderr else ""
    return_code = writer.wait()
    if return_code != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {return_code}:\n{stderr}")
    return frame_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo-file", required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--camera", default="agentview")
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--fps", type=float, default=20.0)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--ffmpeg-path", default=None)
    parser.add_argument("--demo-name", default=None)
    parser.add_argument("--output-prefix", default="")
    args = parser.parse_args()

    demo_file = Path(args.demo_file)
    output_dir = Path(args.output_dir) if args.output_dir else demo_file.parent / "videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_path = get_ffmpeg_path(args.ffmpeg_path)

    with h5py.File(demo_file, "r") as hdf5_file:
        data_attrs = hdf5_file["data"].attrs
        if "env_info" in data_attrs:
            env_kwargs = json.loads(data_attrs["env_info"])
        elif "env_args" in data_attrs:
            env_kwargs = json.loads(data_attrs["env_args"])["env_kwargs"]
        else:
            raise KeyError("Expected data attrs to contain either env_info or env_args")
        problem_info = json.loads(hdf5_file["data"].attrs["problem_info"])
        problem_name = problem_info["problem_name"]
        bddl_file_name = hdf5_file["data"].attrs["bddl_file_name"]

        libero_utils.update_env_kwargs(
            env_kwargs,
            bddl_file_name=bddl_file_name,
            has_renderer=False,
            has_offscreen_renderer=True,
            ignore_done=True,
            use_camera_obs=False,
            camera_names=[args.camera],
            camera_heights=args.height,
            camera_widths=args.width,
            reward_shaping=True,
            control_freq=20,
        )

        env = TASK_MAPPING[problem_name](**env_kwargs)
        try:
            demo_names = [args.demo_name] if args.demo_name else sorted(hdf5_file["data"].keys())
            for demo_name in demo_names:
                if demo_name not in hdf5_file["data"]:
                    raise ValueError(f"{demo_name} not found in {demo_file}")
                output_path = output_dir / f"{args.output_prefix}{demo_name}_{args.camera}.mp4"
                frame_count = render_demo(
                    env,
                    hdf5_file[f"data/{demo_name}"],
                    output_path,
                    args.camera,
                    args.height,
                    args.width,
                    args.fps,
                    args.stride,
                    ffmpeg_path,
                )
                print(f"wrote {output_path} ({frame_count} frames, h264/yuv420p)")
        finally:
            env.close()


if __name__ == "__main__":
    main()
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import textwrap

from icecream import ic

try:
    from .cli import (
        error,
        info,
        success,
        warn,
        todo,
        validate_path_from_cli,
        validate_target_from_cli,
        validate_build_cmd_from_cli,
    )
    from .types import Command
except ImportError:
    """
    This is necessary to safeguard the user from running this script directly
    which will generate errors due to relative importing rules in Python
    """
    print(
        f"You should not run {__file__} as a standalone script.\n"
        f"Use `$ python3 reduce.py {Path(__file__).stem}` instead!",
        file=sys.stderr,
    )
    sys.exit(1)


DEBUG = False
ic.disable()


def make_dot_i_file(
    build_cmd: Command,
    target: Path,
    path_to_linux: Path,
    output_dir: Path,
    force_rm_existing_target: bool,
) -> tuple[Path, str]:
    """
    Make the preprocessed .i file which can then be compiled sans build system

    Returns the path to the .i file as well as the stdout from `make`
    """

    if (abs_target := path_to_linux / target).exists():
        double_check_removal_with_user(
            file=abs_target, force_rm=force_rm_existing_target
        )

    info(f"Making {target}...")
    make_output = subprocess.run(
        [*build_cmd, target], check=False, capture_output=True, cwd=path_to_linux
    )
    ic(make_output)

    destination = output_dir / target.name
    if make_output.returncode == 0:
        info(f"Moving generated {target} file to {output_dir}")
        shutil.move(path_to_linux / target, destination)
        success(f"Successfully generated {target.name}")

    return (destination, make_output.stdout.decode("utf-8"))


def cleanup_dot_i_file(path: Path) -> None:
    """
    Remove preprocessor-specific lines to speed up reductions

    Got some tips from here:
    https://gcc.gnu.org/wiki/A_guide_to_testcase_reduction

    The overhead of this function is worth it. Reductions are sped up greatly.
    """
    info(f"Cleaning up {path.name} file for reduction")
    preprocess_pattern = r"^# .*$"

    file_raw = path.read_text()
    file_raw = re.sub(preprocess_pattern, "", file_raw, flags=re.MULTILINE)

    path.write_text(file_raw)


def get_compiler_invocation(target: Path, make_stdout: str) -> Command:
    """
    Parse out the CC invocation from make's raw output with V=1 on
    """
    pattern = f".*-o {target}.*"
    matches = re.findall(pattern, make_stdout)
    ic(matches)
    assert (
        len(matches) == 1
    ), "Too many (or too few) compiler invocation matches!\n\
            (not your fault, it's prepreduce's fault)"

    main_invocation = matches[0].split()
    main_invocation.insert(-1, "-c")
    return clean_compiler_invocation(main_invocation)


def clean_compiler_invocation(cc_invocation: Command) -> Command:
    """
    Remove all preprocessor flags as well as any relative pathing in invocation
    """

    to_remove = ("-I", "-D", "-Wp", "-include", "-Werror", "./", "-U", "-E")
    rules = [
        (lambda rule: lambda flag: not flag.startswith(rule))(rule)
        for rule in to_remove
    ]

    cleaned = cc_invocation.copy()
    for rule in rules:
        cleaned = filter(rule, cleaned)

    cleaned = list(cleaned)  # eagerly convert iterator to list

    ic(cleaned)

    return cleaned


def cc_invocation_to_flags(cc_invocation: Command) -> str:
    """
    Accepts a full cc_invocation command and parses out just the flags

    The order of the pop()'s are important as the relative index of items
    changes as items are removed
    """
    cc_flags = cc_invocation[1:].copy()  # ditch the `clang` or `gcc` invocation

    dash_o_idx = cc_flags.index("-o")
    cc_flags.pop(dash_o_idx + 1)  # remove target.o
    cc_flags.pop(dash_o_idx)  # remove -o

    dash_c_idx = cc_flags.index("-c")
    cc_flags.pop(dash_c_idx + 1)  # remove target.c
    cc_flags.pop(dash_c_idx)  # remove -c

    return "\n".join([str(x) for x in cc_flags])  # cast is necessary for Paths


def write_flags_txt(cc_flags: str, file_location: Path) -> None:
    """
    Writes compiler flags to a file specified by file_location
    """
    file_location.write_text(cc_flags)
    success(f"Wrote {file_location.name}")


def write_test_script(
    *,
    cc_invocation: Command,
    target: Path,
    output_dir: Path,
    force_rm: bool,
    uses_clang: bool,
    go_fast: bool,
) -> None:
    """
    Create a test.sh script at --output directory
    """
    script_path = output_dir / Path("test.sh")
    info(f"Generating {script_path}")
    if script_path.exists():
        double_check_removal_with_user(file=script_path, force_rm=force_rm)

    cc_flags = cc_invocation_to_flags(cc_invocation)
    flags_output_file = output_dir / Path("flags.txt")

    write_flags_txt(cc_flags, flags_output_file)

    script_text = textwrap.dedent(
        f"""    #!/usr/bin/env bash
    CC_CMD() {{
        {'clang' if uses_clang else 'gcc'} $(cat {flags_output_file.absolute()}) {'-Wfatal-errors' if go_fast else ''} -c {target.with_suffix('.i').name}
    }}
    CC_CMD 2>&1 | grep "<your test here>"
    """
    )  # absolute path of flags.txt is required for cvise

    script_path.write_text(script_text, encoding="utf-8")

    success(f"Successfully wrote {script_path}")
    script_path.chmod(0o755)
    info(f"Added execute permissions to {script_path}")
    todo(
        "Now, modify the last line of test.sh with an interestingness test \n"
        "that properly captures the behavior you're after. After that, "
        "use test.sh with \nreduction tools like cvise.\n"
        "Example Usage: $ cvise test.sh string.i"
    )


def double_check_removal_with_user(*, file: Path, force_rm: bool) -> None:
    # TODO: add optional rename
    while not force_rm:
        warning_msg = warn(
            f"target {file} already exists. Remove it? (y/n): ", ret_only=True
        )
        user_inp = input(warning_msg)
        user_inp = user_inp.strip().lower()
        if user_inp == "y":
            break
        elif user_inp == "n":
            success("OK: quitting.")
            sys.exit(0)
    info(f"Removing {file} which already exists")
    file.unlink()


def setup_argparser(parser: argparse.ArgumentParser) -> None:
    """
    Parse out arguments from command line interface.
    Use various validate_foo_from_cli functions to assist end-user
    """
    global DEBUG

    parser.add_argument(
        "build_command",
        help="The specific build command preamble used sans the target. "
        "Example: `make -j$(nproc) LLVM=1 V=1`",
        nargs="*",
        default=["make", f"-j{os.cpu_count()}", "LLVM=1", "V=1"],
    )

    parser.add_argument(
        "target",
        help="The source file you wish to target. Example: lib/string.o",
        type=validate_target_from_cli,
    )

    parser.add_argument(
        "-p",
        "--path-to-linux",
        type=lambda arg: validate_path_from_cli(arg, "-p/--path-to-linux"),
        default="./",
        help="Specify the Linux source tree directory",
    )

    parser.add_argument(
        "-f",
        "--force-rm-existing-target",
        help="If the target (foo.o) already exists, remove it -- without prompting",
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "-F",
        "--force-rm-existing-script",
        help="If test.sh already exists, remove it -- without prompting",
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "-d",
        "--debug",
        help="Enable prepreduce Debug logs",
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "-o",
        "--output",
        help="Output directory of prepreduce outputs (.i files and test scripts)",
        default=os.getcwd(),
        type=lambda arg: validate_path_from_cli(arg, "-o/--output", allow_mkdir=True),
    )

    parser.add_argument(
        "--no-go-fast",
        help="Disable -Wfatal-errors (will slow down cvise greatly)",
        action="store_true",
        default=False,
    )


def validate_cli_args(cli_args):
    DEBUG = cli_args.debug
    if DEBUG:
        ic.enable()

    validate_build_cmd_from_cli(cli_args.build_command)


def is_kernel_configured_for_clang(path_to_linux: Path) -> bool:
    """
    Find out what compiler to use based on what the kernel build system is
    currently configured for
    """

    config_file = Path(path_to_linux) / Path(".config")
    if not config_file.exists():
        error(
            f"No .config file found at {config_file}, please configure your "
            "kernel build or \n"
            "change your linux build path with --path-to-linux /path/to/linux"
        )  # intentional newline in above error

    clang_kernel_config_opt = "CONFIG_CC_IS_CLANG=y"
    gcc_kernel_config_opt = "CONFIG_CC_IS_GCC=y"
    with config_file.open() as fd:
        for line in fd:
            # option is typically found *very* early in the file,
            # yielding an inexpensive linear search
            line = line.strip()
            if clang_kernel_config_opt in line:
                return True
            if gcc_kernel_config_opt in line:
                return False

    raise EOFError(
        "Upon parsing .config, could not determine gcc or clang usage. "
        f"reduce prep is specifically looking for `{clang_kernel_config_opt}` "
        f"or `{gcc_kernel_config_opt}` in your {config_file} file"
    )


def main(cli_args: argparse.Namespace) -> None:
    validate_cli_args(cli_args=cli_args)

    uses_clang = is_kernel_configured_for_clang(cli_args.path_to_linux)

    info(f"Using CC={'clang' if uses_clang else 'gcc'}")

    ic(cli_args)

    path_to_dot_i_file, make_stdout = make_dot_i_file(
        build_cmd=cli_args.build_command,
        target=cli_args.target,
        path_to_linux=cli_args.path_to_linux,
        output_dir=cli_args.output,
        force_rm_existing_target=cli_args.force_rm_existing_target,
    )

    cleanup_dot_i_file(path_to_dot_i_file)

    cc_invocation = get_compiler_invocation(cli_args.target, make_stdout)
    cc_invocation[
        -1
    ] = cli_args.target.name  # HACK: should search for .c instead of using -1

    ic(cc_invocation)

    write_test_script(
        cc_invocation=cc_invocation,
        target=path_to_dot_i_file.with_suffix(".o"),
        output_dir=cli_args.output,
        force_rm=cli_args.force_rm_existing_script,
        uses_clang=uses_clang,
        go_fast=not cli_args.no_go_fast,
    )


if __name__ == "__main__":
    sys.exit(1)

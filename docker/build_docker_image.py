"""Build the Docker image used by the MNE-Nodes GUI launcher."""

from run_docker_gui import IMAGE, ROOT, run


def main() -> None:
    """Build the MNE-Nodes Docker image."""
    run(
        [
            "docker",
            "build",
            "-f",
            str(ROOT / "docker" / "Dockerfile"),
            "-t",
            IMAGE,
            str(ROOT),
        ]
    )


if __name__ == "__main__":
    main()

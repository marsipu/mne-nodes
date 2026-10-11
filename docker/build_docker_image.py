"""Build the Docker image used by the MNE-Nodes GUI launcher."""

from run_docker_gui import build_image


def main() -> None:
    """Build the MNE-Nodes Docker image."""
    build_image()


if __name__ == "__main__":
    main()

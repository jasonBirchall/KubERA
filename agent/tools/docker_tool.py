import subprocess

class DockerTool:
    def __init__(self, image_name):
        self.image_name = image_name

    def check_docker_image_exists(self) -> bool:
        """
        Returns True if 'docker manifest inspect <image_name>' succeeds,
        otherwise returns False.
        Note: requires Docker installed and a running Docker daemon.
        """
        cmd = ["docker", "manifest", "inspect", self.image_name]
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            return True
        except subprocess.CalledProcessError as e:
            # Non-zero exit code indicates the image probably doesn't exist
            # or there's some networking/credential issue
            return False

    def inspect_docker_image(self) -> str:
        """
        Attempts to run 'docker manifest inspect <image_name>'.
        Returns the output as a string if successful,
        or an error message if not.
        """
        cmd = ["docker", "manifest", "inspect", self.image_name]
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
            return output
        except subprocess.CalledProcessError as e:
            return f"Error inspecting image '{self.image_name}': {e.output.decode()}"


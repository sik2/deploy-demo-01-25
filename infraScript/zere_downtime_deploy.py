import os
import subprocess
import time
import requests
from typing import Dict, Optional

class ServiceManager:
    def __init__(self, socat_port: int = 8081, sleep_duration: int = 3) -> None:
        self.socat_port: int = socat_port
        self.sleep_duration: int = sleep_duration
        self.services: Dict[str, int] = {
            'blog_1': 8082,
            'blog_2': 8083
        }
        self.current_name: Optional[str] = None
        self.current_port: Optional[int] = None
        self.next_name: Optional[str] = None
        self.next_port: Optional[int] = None

    def _find_current_service(self) -> None:
        try:
            cmd = f"ps aux | grep 'socat -t0 TCP-LISTEN:{self.socat_port}' | grep -v grep"
            result = subprocess.getoutput(cmd)
            if result:
                self.current_port = int(result.split(':')[-1])
                self.current_name = next((name for name, port in self.services.items() if port == self.current_port), None)
            else:
                self.current_name, self.current_port = 'blog_2', self.services['blog_2']
        except Exception as e:
            print(f"Error finding current service: {e}")

    def _find_next_service(self) -> None:
        self.next_name, self.next_port = next(
            ((name, port) for name, port in self.services.items() if name != self.current_name),
            (None, None)
        )

    def _remove_container(self, name: str) -> None:
        try:
            subprocess.run(["docker", "stop", name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"Removed container: {name}")
        except Exception as e:
            print(f"Error removing container {name}: {e}")

    def _run_container(self, name: str, port: int) -> None:
        try:
            result = subprocess.run([
                "docker", "run", "-d", "--name", name, "--restart", "unless-stopped",
                "-p", f"{port}:8090", "-e", "TZ=Asia/Seoul",
                "-v", "/dockerProjects/blog/volumes/gen:/gen", "--pull", "always",
                "ghcr.io/sik2/blog"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if result.returncode == 0:
                print(f"Successfully started container: {name}")
            else:
                print(f"Failed to start container {name}: {result.stderr.decode()}")
        except Exception as e:
            print(f"Error running container {name}: {e}")

    def _switch_port(self) -> None:
        try:
            cmd = f"ps aux | grep 'socat -t0 TCP-LISTEN:{self.socat_port}' | grep -v grep | awk '{'{print $2}'}'"
            pid = subprocess.getoutput(cmd)

            if pid:
                os.system(f"kill -15 {pid}")  # Graceful termination

            time.sleep(5)

            subprocess.run([
                "nohup", "socat", f"-t0", f"TCP-LISTEN:{self.socat_port},fork,reuseaddr", f"TCP:localhost:{self.next_port}"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            print(f"Switched port to {self.next_port} using socat")
        except Exception as e:
            print(f"Error switching port: {e}")

    def _is_service_up(self, port: int) -> bool:
        url = f"http://127.0.0.1:{port}/actuator/health"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200 and response.json().get('status') == 'UP':
                return True
        except requests.RequestException:
            pass
        return False

    def update_service(self) -> None:
        self._find_current_service()
        self._find_next_service()

        if not self.next_name or not self.next_port:
            print("Error: Unable to determine next service.")
            return

        self._remove_container(self.next_name)
        self._run_container(self.next_name, self.next_port)

        max_retries = 10
        retries = 0
        while not self._is_service_up(self.next_port) and retries < max_retries:
            print(f"Waiting for {self.next_name} to be 'UP'... ({retries + 1}/{max_retries})")
            time.sleep(self.sleep_duration)
            retries += 1

        if retries == max_retries:
            print(f"Error: Service {self.next_name} failed to start.")
            return

        self._switch_port()

        if self.current_name:
            self._remove_container(self.current_name)

        print("Switched service successfully!")

if __name__ == "__main__":
    manager = ServiceManager()
    manager.update_service()

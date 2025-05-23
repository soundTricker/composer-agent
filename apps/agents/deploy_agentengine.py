import json
import os

import requests
import vertexai
from google.adk.artifacts import GcsArtifactService
from vertexai import agent_engines
import dotenv

dotenv.load_dotenv()
vertexai.init(
    project=os.environ.get('GOOGLE_CLOUD_PROJECT'),
    location=os.environ.get('GOOGLE_CLOUD_LOCATION'),
    staging_bucket=os.environ.get('STAGING_BUCKET')
)

SETTING_FILENAME = ".agentengine.json"

bucket = os.environ.get('ARTIFACT_BUCKET')
def generate_artifact_service():
    # TODO
    return GcsArtifactService(bucket)

def deploy_agentengine():
    from composer.agent import root_agent
    from composer.agentengine import CustomAdkApp

    adk_app = CustomAdkApp(agent=root_agent, enable_tracing=True, artifact_service_builder=generate_artifact_service)

    if not os.path.exists("composer/ffmpeg-7.0.2-amd64-static"):
        res = requests.get("https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz")
        res.raise_for_status()
        with open("composer/ffmpeg-release-amd64-static.tar.xz", mode='wb') as fp:
            fp.write(res.content)

        import tarfile
        with tarfile.open("composer/ffmpeg-release-amd64-static.tar.xz", mode='r:xz') as tar:
            tar.extractall("composer")
        os.remove("composer/ffmpeg-release-amd64-static.tar.xz")

    packages = [
        "composer"
    ]

    # TODO https://github.com/google/adk-python/issues/808
    requirements = [
        "google-adk==0.5.0",
        "pydub>=0.25.1",
        "google-cloud-aiplatform[adk, agent_engines]==1.94.0",
        "nest-asyncio>=1.6.0"
    ]
    display_name = "ComposerAgent"


    if os.path.isfile(SETTING_FILENAME):
        print("setting file found")

        with open(SETTING_FILENAME, mode='r') as fp:
            settings = json.load(fp)
            agent_engine_id = settings["agent_engine_id"]
            agent_engine = agent_engines.get(agent_engine_id)
            print(f"start updating {agent_engine_id}")
            agent_engine.update(
                agent_engine=adk_app,
                display_name=display_name,
                requirements=requirements,
                extra_packages=packages
            )
        return

    print("setting file not found")
    print("create new agent engine instance")
    agent_engine = agent_engines.create(
        agent_engine=adk_app,
        display_name=display_name,
        requirements=requirements,
        extra_packages=packages,
    )
    print(f"Done creating new agent engine instance. resource name: {agent_engine.resource_name}")
    with open(SETTING_FILENAME, mode="w") as fp:
        print(f"Create setting file to {fp.name}")
        json.dump({
            "agent_engine_id": agent_engine.resource_name,
        }, fp)

if __name__ == "__main__":
    deploy_agentengine()

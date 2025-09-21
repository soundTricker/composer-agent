import json
import os

import dotenv
import vertexai
from google.adk.artifacts import GcsArtifactService
from vertexai import agent_engines

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

    adk_app = CustomAdkApp(
        agent=root_agent,
        enable_tracing=True,
        artifact_service_builder=generate_artifact_service
    )

    packages = [
        "composer",
        "installation_scripts/install.sh"
    ]

    requirements = [
        "google-adk==1.14.1",
        "pydub>=0.25.1",
        "google-cloud-aiplatform[adk, agent_engines]==1.115.0"
    ]
    display_name = "ComposerAgent"

    env_vers = {"GEMINI_API_KEY": os.environ.get('GEMINI_API_KEY')}
    build_options = {"installation_scripts": ["installation_scripts/install.sh"]}
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
                extra_packages=packages,
                build_options=build_options,
                env_vars=env_vers,
            )
        return

    print("setting file not found")
    print("create new agent engine instance")
    agent_engine = agent_engines.create(
        agent_engine=adk_app,
        display_name=display_name,
        requirements=requirements,
        extra_packages=packages,
        build_options=build_options,
        env_vars=env_vers
    )
    print(f"Done creating new agent engine instance. resource name: {agent_engine.resource_name}")
    with open(SETTING_FILENAME, mode="w") as fp:
        print(f"Create setting file to {fp.name}")
        json.dump({
            "agent_engine_id": agent_engine.resource_name,
        }, fp)

if __name__ == "__main__":
    deploy_agentengine()

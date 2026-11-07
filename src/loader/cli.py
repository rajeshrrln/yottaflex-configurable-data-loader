import argparse, json
from .pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Metadata-driven data loader")
    parser.add_argument("--config", required=True, help="YAML configuration path")
    parser.add_argument("--run-id", help="Optional deterministic run ID")
    args = parser.parse_args()
    print(json.dumps(run_pipeline(args.config, args.run_id), indent=2))

if __name__ == "__main__": main()

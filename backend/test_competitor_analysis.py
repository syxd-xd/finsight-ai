import json

from agents.competitor_analysis import analyze_competitors


if __name__ == "__main__":

    result = analyze_competitors(
        target_ticker="AAPL"
    )

    print(json.dumps(result, indent=2))

"""
RAGAS Evaluation Runner
========================

Evaluates PokeAgent answer quality using RAGAS metrics:

  - faithfulness:       Does the answer stick to the retrieved context?
  - answer_relevancy:   Does the answer actually address the question?
  - context_precision:  Is the retrieved context relevant to the question?

HOW IT WORKS:
1. Load the hand-labeled test_set.json
2. For each question, run the PokeAgent to get an answer + tool outputs
3. Feed (question, answer, context, ground_truth) to RAGAS
4. Save a markdown report

USAGE:
    python -m evals.run_evals
    # or run a subset:
    python -m evals.run_evals --category lore --limit 5

RAGAS docs: https://docs.ragas.io/
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Ensure project root on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_test_set(category: str = None, limit: int = None) -> List[Dict]:
    """Load and optionally filter the hand-labeled test set."""
    test_set_path = Path(__file__).parent / "test_set.json"

    with open(test_set_path, "r") as f:
        # Strip JS-style comments before parsing (our JSON uses // comments)
        raw = f.read()
        lines = [l for l in raw.splitlines() if not l.strip().startswith("//")]
        data = json.loads("\n".join(lines))

    questions = data["questions"]

    if category:
        questions = [q for q in questions if q["category"] == category]

    if limit:
        questions = questions[:limit]

    logger.info(f"Loaded {len(questions)} test questions")
    return questions


def run_agent_on_question(agent, question: str) -> Dict[str, Any]:
    """
    Run the PokeAgent on a single question.

    Returns dict with keys: answer, tool_calls, contexts
    """
    result = agent.run(question)

    # Collect tool outputs as contexts for RAGAS
    contexts = []
    for tc in result.get("tool_calls", []):
        output = tc.get("output")
        if output:
            contexts.append(json.dumps(output))

    return {
        "answer": result["answer"],
        "tool_calls": result["tool_calls"],
        "contexts": contexts,
    }


def build_ragas_dataset(test_questions: List[Dict], agent) -> Dict:
    """
    Run agent on all test questions and format results for RAGAS.

    RAGAS expects a dataset with columns:
        question, answer, contexts, ground_truth
    """
    questions = []
    answers = []
    contexts = []
    ground_truths = []

    for i, item in enumerate(test_questions):
        logger.info(f"[{i+1}/{len(test_questions)}] {item['id']}: {item['question'][:50]}...")

        try:
            result = run_agent_on_question(agent, item["question"])
            questions.append(item["question"])
            answers.append(result["answer"])
            contexts.append(result["contexts"] if result["contexts"] else ["No context retrieved"])
            ground_truths.append(item["ground_truth"])
        except Exception as e:
            logger.error(f"  Error on {item['id']}: {e}")
            questions.append(item["question"])
            answers.append(f"ERROR: {e}")
            contexts.append(["Error"])
            ground_truths.append(item["ground_truth"])

    return {
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    }


def run_ragas_evaluation(dataset_dict: Dict) -> Dict:
    """
    Run RAGAS metrics on the collected answers.

    Returns dict of metric_name -> score.
    """
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision

        dataset = Dataset.from_dict(dataset_dict)

        logger.info("Running RAGAS evaluation (this calls OpenAI)...")
        result = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_precision]
        )
        return dict(result)

    except ImportError as e:
        logger.error(f"RAGAS/datasets not installed: {e}")
        return {"error": str(e)}


def save_report(scores: Dict, dataset_dict: Dict, output_path: str = None) -> str:
    """Save results as a markdown report."""
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"evals/report_{ts}.md"

    lines = [
        "# PokeAgent Evaluation Report",
        f"\nGenerated: {datetime.now().isoformat()}",
        "\n## RAGAS Scores\n",
        "| Metric | Score |",
        "|--------|-------|",
    ]

    for metric, score in scores.items():
        if metric != "error":
            lines.append(f"| {metric} | {score:.4f} |")

    lines += [
        "\n## Per-Question Results\n",
        "| # | Question | Answer (truncated) |",
        "|---|----------|---------------------|",
    ]

    for i, (q, a) in enumerate(zip(dataset_dict["question"], dataset_dict["answer"]), 1):
        lines.append(f"| {i} | {q[:60]} | {a[:80]} |")

    report = "\n".join(lines)
    Path(output_path).write_text(report)
    logger.info(f"Report saved to {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Run RAGAS evals on PokeAgent")
    parser.add_argument("--category", type=str, default=None,
                        help="Filter to a specific category: lore, stats, type_matchup, recommendation, multi_hop")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max number of questions to evaluate")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip RAGAS scoring, just print agent answers")
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not set in .env — agent will not work")
        sys.exit(1)

    # Initialize agent
    from agent.agent import PokeAgent
    logger.info("Initializing PokeAgent...")
    agent = PokeAgent()

    # Load test questions
    test_questions = load_test_set(category=args.category, limit=args.limit)

    # Run agent on each question
    dataset_dict = build_ragas_dataset(test_questions, agent)

    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN — Agent answers (no RAGAS scoring)")
        print("=" * 60)
        for q, a, ctx in zip(dataset_dict["question"], dataset_dict["answer"], dataset_dict["contexts"]):
            print(f"\nQ: {q}")
            print(f"A: {a[:200]}")
            print(f"Contexts used: {len(ctx)}")
        return

    # Run RAGAS
    scores = run_ragas_evaluation(dataset_dict)

    print("\n" + "=" * 60)
    print("RAGAS Evaluation Results")
    print("=" * 60)
    for metric, score in scores.items():
        print(f"  {metric}: {score:.4f}")

    # Save report
    report_path = save_report(scores, dataset_dict)
    print(f"\nReport saved: {report_path}")


if __name__ == "__main__":
    main()

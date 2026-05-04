from __future__ import annotations

from agent_tools.registry import assess_agent_access, find_agents, load_agents, load_profiles, recommend_profile


class TestTrainingFocusedAgents:
    def setup_method(self) -> None:
        self.agents = load_agents()
        self.profiles = load_profiles()

    def test_training_focused_agents_are_registered(self) -> None:
        expected = {
            "agent-evals-engineer": ("balanced", "medium"),
            "agent-observability-engineer": ("balanced", "medium"),
            "feedback-learning-engineer": ("balanced", "medium"),
            "grounding-engineer": ("balanced", "medium"),
            "ai-incident-responder": ("power", "high"),
        }

        for agent_id, (preferred_profile, risk_level) in expected.items():
            agent = self.agents.get(agent_id)
            assert agent is not None, f"Missing agent {agent_id}"
            assert agent.preferred_profile == preferred_profile
            assert agent.risk_level == risk_level

    def test_training_focused_agents_expose_expected_capabilities(self) -> None:
        expected = {
            "agent-evals-engineer": {"eval-design", "regression-detection", "failure-taxonomy"},
            "agent-observability-engineer": {"trace-instrumentation", "cost-analysis", "drift-detection"},
            "feedback-learning-engineer": {"feedback-triage", "correction-dataset-curation", "continuous-improvement"},
            "grounding-engineer": {"retrieval-tuning", "citation-design", "hallucination-reduction"},
            "ai-incident-responder": {"incident-triage", "rollback-planning", "guardrail-hardening"},
        }

        for agent_id, capabilities in expected.items():
            agent = self.agents[agent_id]
            assert capabilities.issubset(set(agent.capabilities))

    def test_recommended_profiles_cover_required_tools(self) -> None:
        for agent_id in (
            "agent-evals-engineer",
            "agent-observability-engineer",
            "feedback-learning-engineer",
            "grounding-engineer",
            "ai-incident-responder",
        ):
            agent = self.agents[agent_id]
            profile = recommend_profile(agent, self.profiles)
            report = assess_agent_access(agent, profile)
            assert report["pass"] is True
            assert report["profile"] == agent.preferred_profile

    def test_find_agents_matches_training_queries(self) -> None:
        eval_matches = {agent.id for agent in find_agents(self.agents, "evaluation")}
        grounding_matches = {agent.id for agent in find_agents(self.agents, "grounding")}
        incident_matches = {agent.id for agent in find_agents(self.agents, "incident")}

        assert "agent-evals-engineer" in eval_matches
        assert "grounding-engineer" in grounding_matches
        assert "ai-incident-responder" in incident_matches

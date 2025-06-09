"""
ReAct Agent for Kubernetes Pod Failure Diagnosis

This module implements the ReAct (Reasoning + Acting) loop for iterative
Kubernetes troubleshooting with hypothesis generation, targeted information
gathering, and confidence refinement.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict

from .react_hypothesis import (
    Hypothesis, HypothesisType, KubernetesHypotheses, HypothesisScorer
)
from .react_information_gatherer import InformationGatherer, GatheringResult
from .data_anonymizer import DataAnonymizer

logger = logging.getLogger(__name__)


@dataclass
class ReActIteration:
    """Represents one iteration of the ReAct loop"""
    iteration_number: int
    hypotheses: List[Hypothesis]
    selected_hypothesis: Optional[Hypothesis]
    gathered_evidence: Dict[str, Any]
    confidence_updates: Dict[str, float]
    reasoning_summary: str
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration_number": self.iteration_number,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "selected_hypothesis": self.selected_hypothesis.to_dict() if self.selected_hypothesis else None,
            "gathered_evidence": self.gathered_evidence,
            "confidence_updates": self.confidence_updates,
            "reasoning_summary": self.reasoning_summary,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class ReActDiagnosisResult:
    """Final result of ReAct diagnosis process"""
    final_diagnosis: str
    best_hypothesis: Hypothesis
    confidence_score: float
    iterations: List[ReActIteration]
    total_commands_executed: int
    total_execution_time: float
    reasoning_trace: List[str]
    actionable_recommendations: List[str]
    kubectl_commands_used: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_diagnosis": self.final_diagnosis,
            "best_hypothesis": self.best_hypothesis.to_dict(),
            "confidence_score": self.confidence_score,
            "iterations": [it.to_dict() for it in self.iterations],
            "total_commands_executed": self.total_commands_executed,
            "total_execution_time": self.total_execution_time,
            "reasoning_trace": self.reasoning_trace,
            "actionable_recommendations": self.actionable_recommendations,
            "kubectl_commands_used": self.kubectl_commands_used
        }


class ReActAgent:
    """
    ReAct Agent for iterative Kubernetes diagnosis
    
    Implements the Reasoning + Acting loop:
    1. Generate hypotheses about the problem
    2. Select the most promising hypothesis to investigate
    3. Gather targeted evidence using kubectl commands
    4. Update hypothesis confidence based on evidence
    5. Repeat until confident diagnosis is reached
    """
    
    def __init__(self, 
                 llm_client=None,
                 max_iterations: int = 3,
                 confidence_threshold: float = 8.0,
                 enable_anonymization: bool = True,
                 command_timeout: int = 30):
        """
        Initialize ReAct Agent
        
        Args:
            llm_client: OpenAI client for LLM calls
            max_iterations: Maximum number of ReAct iterations
            confidence_threshold: Stop when hypothesis reaches this confidence
            enable_anonymization: Whether to anonymize data before LLM calls
            command_timeout: Timeout for kubectl commands
        """
        self.llm_client = llm_client
        self.max_iterations = max_iterations
        self.confidence_threshold = confidence_threshold
        self.enable_anonymization = enable_anonymization
        self.command_timeout = command_timeout
        
        # Initialize components
        self.information_gatherer = InformationGatherer(timeout=command_timeout)
        self.anonymizer = DataAnonymizer() if enable_anonymization else None
        
        # Tracking variables
        self.iterations: List[ReActIteration] = []
        self.reasoning_trace: List[str] = []
        self.kubectl_commands_used: List[str] = []
        self.start_time: Optional[datetime] = None
    
    async def diagnose(self, initial_metadata: Dict[str, Any]) -> ReActDiagnosisResult:
        """
        Main entry point for ReAct diagnosis
        
        Args:
            initial_metadata: Initial pod metadata from k8s_tool.gather_metadata()
            
        Returns:
            ReActDiagnosisResult with complete diagnosis and reasoning trace
        """
        self.start_time = datetime.now()
        self.iterations.clear()
        self.reasoning_trace.clear()
        self.kubectl_commands_used.clear()
        
        logger.info(f"Starting ReAct diagnosis for pod {initial_metadata.get('pod_name', 'unknown')}")
        
        try:
            # Step 1: Generate initial hypotheses
            self.reasoning_trace.append("🧠 REASONING: Generating initial hypotheses from pod metadata")
            hypotheses = KubernetesHypotheses.generate_initial_hypotheses(initial_metadata)
            
            if not hypotheses:
                return self._create_fallback_result("No viable hypotheses generated from metadata")
            
            self.reasoning_trace.append(f"Generated {len(hypotheses)} initial hypotheses")
            
            # Step 2: Execute ReAct loop
            for iteration in range(self.max_iterations):
                self.reasoning_trace.append(f"\n🔄 ITERATION {iteration + 1}")
                
                iteration_result = await self._execute_iteration(
                    iteration + 1, hypotheses, initial_metadata
                )
                
                self.iterations.append(iteration_result)
                
                # Check stopping criteria
                best_hypothesis = max(hypotheses, key=lambda h: h.confidence)
                if best_hypothesis.confidence >= self.confidence_threshold:
                    self.reasoning_trace.append(
                        f"✅ Reached confidence threshold ({best_hypothesis.confidence:.1f} >= {self.confidence_threshold})"
                    )
                    break
                
                # Prepare for next iteration
                hypotheses = HypothesisScorer.prioritize_hypotheses(hypotheses)
            
            # Step 3: Generate final diagnosis
            return await self._generate_final_diagnosis(hypotheses, initial_metadata)
            
        except Exception as e:
            logger.error(f"ReAct diagnosis failed: {str(e)}", exc_info=True)
            return self._create_error_result(str(e))
    
    async def _execute_iteration(self, 
                                iteration_number: int, 
                                hypotheses: List[Hypothesis], 
                                metadata: Dict[str, Any]) -> ReActIteration:
        """Execute one iteration of the ReAct loop"""
        
        # REASONING: Select hypothesis to investigate
        selected_hypothesis = self._select_hypothesis_to_investigate(hypotheses)
        
        self.reasoning_trace.append(
            f"🎯 SELECTED: {selected_hypothesis.type.value} "
            f"(confidence: {selected_hypothesis.confidence:.1f})"
        )
        
        # ACTING: Gather targeted evidence
        self.reasoning_trace.append("⚡ ACTING: Gathering targeted evidence...")
        gathered_evidence = await self.information_gatherer.gather_for_hypothesis(
            selected_hypothesis, metadata
        )
        
        # Track commands used
        for command in selected_hypothesis.kubectl_commands[:3]:  # Limit for performance
            if command not in self.kubectl_commands_used:
                self.kubectl_commands_used.append(command)
        
        # Update hypothesis confidence based on evidence
        confidence_updates = {}
        for hypothesis in hypotheses:
            old_confidence = hypothesis.confidence
            
            # Update confidence for all hypotheses based on new evidence
            if hypothesis.id == selected_hypothesis.id:
                # More detailed update for the investigated hypothesis
                HypothesisScorer.update_confidence(hypothesis, gathered_evidence)
            else:
                # Basic update for other hypotheses based on conflicting evidence
                self._update_competing_hypothesis(hypothesis, gathered_evidence, selected_hypothesis)
            
            confidence_updates[hypothesis.id] = hypothesis.confidence - old_confidence
        
        # Generate reasoning summary for this iteration
        reasoning_summary = self._generate_iteration_summary(
            selected_hypothesis, gathered_evidence, confidence_updates
        )
        
        self.reasoning_trace.append(f"📊 UPDATED CONFIDENCE: {reasoning_summary}")
        
        return ReActIteration(
            iteration_number=iteration_number,
            hypotheses=hypotheses.copy(),
            selected_hypothesis=selected_hypothesis,
            gathered_evidence=gathered_evidence,
            confidence_updates=confidence_updates,
            reasoning_summary=reasoning_summary,
            timestamp=datetime.now()
        )
    
    def _select_hypothesis_to_investigate(self, hypotheses: List[Hypothesis]) -> Hypothesis:
        """
        Select the most promising hypothesis to investigate next
        
        Balances:
        - Current confidence level
        - Potential impact (severity)
        - Ease of validation
        - Information gap (uncertainty)
        """
        # Prioritize hypotheses and return the top one
        prioritized = HypothesisScorer.prioritize_hypotheses(hypotheses)
        return prioritized[0]
    
    def _update_competing_hypothesis(self, 
                                   hypothesis: Hypothesis, 
                                   evidence: Dict[str, Any], 
                                   investigated_hypothesis: Hypothesis):
        """Update confidence for hypotheses that weren't directly investigated"""
        
        # If evidence strongly supports another hypothesis type, 
        # reduce confidence in competing hypotheses
        if evidence.get("findings"):
            findings_text = " ".join(evidence["findings"]).lower()
            
            # Check if evidence contradicts this hypothesis
            if hypothesis.type != investigated_hypothesis.type:
                contradictory_terms = self._get_contradictory_terms(hypothesis.type)
                
                for term in contradictory_terms:
                    if term in findings_text:
                        hypothesis.confidence = max(0.0, hypothesis.confidence - 0.5)
                        hypothesis.evidence_against.append(f"Evidence contradicts: {term}")
    
    def _get_contradictory_terms(self, hypothesis_type: HypothesisType) -> List[str]:
        """Get terms that would contradict a hypothesis"""
        contradictory_map = {
            HypothesisType.RESOURCE_EXHAUSTION: [
                "memory usage normal", "cpu usage normal", "no resource events"
            ],
            HypothesisType.IMAGE_REGISTRY_ISSUES: [
                "successful image pulls", "valid image config"
            ],
            HypothesisType.CONFIGURATION_ERRORS: [
                "configuration valid", "successful mounts"
            ],
            HypothesisType.LIVENESS_READINESS: [
                "probes passing", "application healthy"
            ]
        }
        
        return contradictory_map.get(hypothesis_type, [])
    
    def _generate_iteration_summary(self, 
                                  hypothesis: Hypothesis, 
                                  evidence: Dict[str, Any], 
                                  confidence_updates: Dict[str, float]) -> str:
        """Generate human-readable summary of iteration results"""
        findings = evidence.get("findings", [])
        
        if findings:
            findings_text = "; ".join(findings[:3])  # Limit to top 3 findings
            return f"{hypothesis.type.value}: {findings_text}"
        else:
            return f"{hypothesis.type.value}: No significant evidence found"
    
    async def _generate_final_diagnosis(self, 
                                      hypotheses: List[Hypothesis], 
                                      initial_metadata: Dict[str, Any]) -> ReActDiagnosisResult:
        """Generate the final diagnosis using LLM with all gathered evidence"""
        
        best_hypothesis = max(hypotheses, key=lambda h: h.confidence)
        
        # Prepare data for LLM analysis
        diagnosis_context = {
            "pod_metadata": initial_metadata,
            "react_iterations": [it.to_dict() for it in self.iterations],
            "final_hypotheses": [h.to_dict() for h in hypotheses],
            "best_hypothesis": best_hypothesis.to_dict(),
            "reasoning_trace": self.reasoning_trace
        }
        
        # Generate final diagnosis using LLM
        if self.llm_client:
            final_diagnosis = await self._llm_generate_diagnosis(diagnosis_context)
            actionable_recommendations = await self._llm_generate_recommendations(diagnosis_context)
        else:
            final_diagnosis = self._fallback_diagnosis(best_hypothesis)
            actionable_recommendations = self._fallback_recommendations(best_hypothesis)
        
        # Calculate total execution time
        total_time = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0.0
        
        self.reasoning_trace.append(f"\n🎯 FINAL DIAGNOSIS: {final_diagnosis}")
        
        return ReActDiagnosisResult(
            final_diagnosis=final_diagnosis,
            best_hypothesis=best_hypothesis,
            confidence_score=best_hypothesis.confidence,
            iterations=self.iterations,
            total_commands_executed=len(self.kubectl_commands_used),
            total_execution_time=total_time,
            reasoning_trace=self.reasoning_trace,
            actionable_recommendations=actionable_recommendations,
            kubectl_commands_used=self.kubectl_commands_used
        )
    
    async def _llm_generate_diagnosis(self, context: Dict[str, Any]) -> str:
        """Use LLM to generate final diagnosis from ReAct evidence"""
        
        # Anonymize data if enabled
        session_map = {}
        if self.enable_anonymization and self.anonymizer:
            context, session_map = self.anonymizer.anonymize_data(context)
        
        system_prompt = """
        You are a Kubernetes expert analyzing the results of a systematic ReAct diagnosis process.
        
        You have been given:
        1. Initial pod metadata
        2. Multiple ReAct iterations showing hypothesis testing
        3. Evidence gathered through targeted kubectl commands
        4. Confidence scores for different failure hypotheses
        
        Based on this systematic investigation, provide a confident, specific diagnosis of the root cause.
        
        Format your response as:
        === ROOT CAUSE ANALYSIS ===
        [Specific diagnosis based on the evidence]
        
        === CONFIDENCE ASSESSMENT ===
        [Why you're confident in this diagnosis]
        
        === SUPPORTING EVIDENCE ===
        [Key evidence that supports this conclusion]
        """
        
        user_prompt = f"""
        Analyze this ReAct diagnosis investigation:
        
        BEST HYPOTHESIS: {context['best_hypothesis']['description']} 
        (Confidence: {context['best_hypothesis']['confidence']:.1f}/10.0)
        
        INVESTIGATION SUMMARY:
        {json.dumps(context['react_iterations'], indent=2)}
        
        REASONING TRACE:
        {chr(10).join(context['reasoning_trace'])}
        
        Provide your final diagnosis based on this systematic investigation.
        """
        
        try:
            if hasattr(self.llm_client, 'chat') and hasattr(self.llm_client.chat, 'completions'):
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.llm_client.chat.completions.create(
                        model="gpt-4",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.3
                    )
                )
                diagnosis = response.choices[0].message.content
            else:
                # Fallback for different LLM client interfaces
                diagnosis = self._fallback_diagnosis(context['best_hypothesis'])
            
            # Deanonymize if needed
            if self.enable_anonymization and self.anonymizer and session_map:
                diagnosis = self.anonymizer.deanonymize_response(diagnosis, session_map)
            
            return diagnosis
            
        except Exception as e:
            logger.error(f"LLM diagnosis generation failed: {e}")
            return self._fallback_diagnosis(context['best_hypothesis'])
    
    async def _llm_generate_recommendations(self, context: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations using LLM"""
        
        try:
            system_prompt = """
            Based on the ReAct diagnosis results, provide 3-5 specific, actionable recommendations 
            for resolving this Kubernetes issue. Each recommendation should be:
            1. Specific and actionable
            2. Prioritized by importance
            3. Include relevant kubectl commands where applicable
            
            Format as a numbered list.
            """
            
            user_prompt = f"""
            Diagnosis: {context['best_hypothesis']['description']}
            Evidence: {json.dumps(context['react_iterations'][-1]['gathered_evidence'], indent=2)}
            
            Provide actionable recommendations to resolve this issue.
            """
            
            if hasattr(self.llm_client, 'chat') and hasattr(self.llm_client.chat, 'completions'):
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.llm_client.chat.completions.create(
                        model="gpt-4",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.4
                    )
                )
                recommendations_text = response.choices[0].message.content
                
                # Parse numbered list
                recommendations = []
                for line in recommendations_text.split('\n'):
                    line = line.strip()
                    if line and (line[0].isdigit() or line.startswith('-')):
                        # Clean up numbering
                        if line[0].isdigit() and '. ' in line:
                            clean_line = line[line.find('. ') + 2:]
                        elif line.startswith('- '):
                            clean_line = line[2:]
                        else:
                            clean_line = line
                        recommendations.append(clean_line)
                
                return recommendations[:5]  # Limit to 5 recommendations
            
        except Exception as e:
            logger.error(f"LLM recommendation generation failed: {e}")
        
        return self._fallback_recommendations(context['best_hypothesis'])
    
    def _fallback_diagnosis(self, best_hypothesis: Dict[str, Any]) -> str:
        """Fallback diagnosis when LLM is unavailable"""
        return f"""
        === ROOT CAUSE ANALYSIS ===
        Based on systematic investigation, the most likely cause is {best_hypothesis['description']}.
        
        === CONFIDENCE ASSESSMENT ===
        Confidence level: {best_hypothesis['confidence']:.1f}/10.0
        
        === SUPPORTING EVIDENCE ===
        Evidence collected through targeted kubectl command execution supports this hypothesis.
        """
    
    def _fallback_recommendations(self, best_hypothesis: Dict[str, Any]) -> List[str]:
        """Fallback recommendations when LLM is unavailable"""
        hypothesis_type = best_hypothesis.get('type', 'unknown')
        
        recommendation_map = {
            'resource_exhaustion': [
                "Check and adjust resource limits and requests",
                "Monitor node resource usage with kubectl top nodes",
                "Consider horizontal pod autoscaling if applicable"
            ],
            'image_registry_issues': [
                "Verify image name and tag correctness",
                "Check registry authentication and pull secrets",
                "Test registry connectivity from the cluster"
            ],
            'configuration_errors': [
                "Validate ConfigMap and Secret configurations",
                "Check environment variable references",
                "Verify volume mount paths and permissions"
            ],
            'liveness_readiness': [
                "Review and adjust probe configurations",
                "Check application startup time and health endpoints",
                "Monitor probe failure events"
            ]
        }
        
        return recommendation_map.get(hypothesis_type, [
            "Review pod describe output for error details",
            "Check cluster events for related issues",
            "Consult Kubernetes documentation for the specific error"
        ])
    
    def _create_fallback_result(self, message: str) -> ReActDiagnosisResult:
        """Create a fallback result when ReAct process cannot proceed"""
        fallback_hypothesis = Hypothesis(
            id="fallback",
            type=HypothesisType.CONFIGURATION_ERRORS,  # Generic fallback
            description=message,
            confidence=1.0,
            evidence_for=[],
            evidence_against=[],
            needed_data=[],
            kubectl_commands=[],
            severity_score=5.0,
            ease_of_validation=1.0
        )
        
        return ReActDiagnosisResult(
            final_diagnosis=message,
            best_hypothesis=fallback_hypothesis,
            confidence_score=1.0,
            iterations=[],
            total_commands_executed=0,
            total_execution_time=0.0,
            reasoning_trace=[message],
            actionable_recommendations=["Review pod configuration manually"],
            kubectl_commands_used=[]
        )
    
    def _create_error_result(self, error_message: str) -> ReActDiagnosisResult:
        """Create an error result when ReAct process fails"""
        error_hypothesis = Hypothesis(
            id="error",
            type=HypothesisType.CONFIGURATION_ERRORS,
            description=f"ReAct diagnosis failed: {error_message}",
            confidence=0.0,
            evidence_for=[],
            evidence_against=[],
            needed_data=[],
            kubectl_commands=[],
            severity_score=1.0,
            ease_of_validation=1.0
        )
        
        return ReActDiagnosisResult(
            final_diagnosis=f"Diagnosis failed: {error_message}",
            best_hypothesis=error_hypothesis,
            confidence_score=0.0,
            iterations=self.iterations,
            total_commands_executed=len(self.kubectl_commands_used),
            total_execution_time=(datetime.now() - self.start_time).total_seconds() if self.start_time else 0.0,
            reasoning_trace=self.reasoning_trace + [f"ERROR: {error_message}"],
            actionable_recommendations=["Check system logs and try manual diagnosis"],
            kubectl_commands_used=self.kubectl_commands_used
        )
    
    def get_iteration_summary(self) -> str:
        """Get a human-readable summary of all iterations"""
        if not self.iterations:
            return "No iterations completed"
        
        summary_lines = ["ReAct Diagnosis Summary:", "=" * 30]
        
        for iteration in self.iterations:
            summary_lines.append(f"\nIteration {iteration.iteration_number}:")
            if iteration.selected_hypothesis:
                summary_lines.append(f"  Investigated: {iteration.selected_hypothesis.type.value}")
                summary_lines.append(f"  Confidence: {iteration.selected_hypothesis.confidence:.1f}")
            summary_lines.append(f"  Summary: {iteration.reasoning_summary}")
        
        return "\n".join(summary_lines)
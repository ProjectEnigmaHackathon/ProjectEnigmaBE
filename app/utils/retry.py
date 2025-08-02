"""
Retry and Recovery Utilities

This module provides comprehensive retry mechanisms with exponential backoff,
circuit breaker patterns, and error recovery strategies for API integrations.
"""

import asyncio
import functools
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, Union

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


class RetryStrategy(str, Enum):
    """Retry strategy enumeration."""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_INTERVAL = "fixed_interval"
    CUSTOM = "custom"


class CircuitBreakerState(str, Enum):
    """Circuit breaker state enumeration."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RetryConfig(BaseModel):
    """Configuration for retry behavior."""
    max_attempts: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    retryable_exceptions: List[Type[Exception]] = []
    non_retryable_exceptions: List[Type[Exception]] = []


class CircuitBreakerConfig(BaseModel):
    """Configuration for circuit breaker."""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    expected_exception: Type[Exception] = Exception


class RetryStats(BaseModel):
    """Statistics for retry operations."""
    total_attempts: int = 0
    successful_attempts: int = 0
    failed_attempts: int = 0
    last_attempt_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    average_response_time: float = 0.0


class CircuitBreaker:
    """
    Circuit breaker implementation for handling cascading failures.
    
    Prevents repeated calls to failing services and allows recovery.
    """
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.stats = RetryStats()
        
    def is_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self.state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has passed
            if (self.last_failure_time and 
                time.time() - self.last_failure_time >= self.config.recovery_timeout):
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("Circuit breaker transitioning to half-open", 
                          failure_count=self.failure_count)
                return False
            return True
        return False
    
    def record_success(self):
        """Record a successful operation."""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
        self.stats.successful_attempts += 1
        self.stats.last_success_time = datetime.utcnow()
        
        logger.debug("Circuit breaker success recorded", state=self.state.value)
    
    def record_failure(self):
        """Record a failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.stats.failed_attempts += 1
        self.stats.last_failure_time = datetime.utcnow()
        
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning("Circuit breaker opened", 
                         failure_count=self.failure_count,
                         threshold=self.config.failure_threshold)
        
        logger.debug("Circuit breaker failure recorded", 
                    failure_count=self.failure_count,
                    state=self.state.value)


class RetryableError(Exception):
    """Base exception for retryable errors."""
    pass


class NonRetryableError(Exception):
    """Base exception for non-retryable errors."""
    pass


class RetryExhaustedError(Exception):
    """Exception raised when all retry attempts are exhausted."""
    
    def __init__(self, message: str, attempts: int, last_exception: Exception):
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(message)


def calculate_delay(
    attempt: int, 
    config: RetryConfig, 
    custom_delays: Optional[List[float]] = None
) -> float:
    """Calculate delay before next retry attempt."""
    if config.strategy == RetryStrategy.CUSTOM and custom_delays:
        if attempt - 1 < len(custom_delays):
            base_delay = custom_delays[attempt - 1]
        else:
            base_delay = custom_delays[-1]
    elif config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
        base_delay = config.base_delay * (config.backoff_multiplier ** (attempt - 1))
    elif config.strategy == RetryStrategy.LINEAR_BACKOFF:
        base_delay = config.base_delay * attempt
    else:  # FIXED_INTERVAL
        base_delay = config.base_delay
    
    # Apply max delay limit
    delay = min(base_delay, config.max_delay)
    
    # Add jitter to prevent thundering herd
    if config.jitter:
        import random
        jitter_factor = random.uniform(0.5, 1.5)
        delay *= jitter_factor
    
    return delay


def is_retryable_exception(
    exception: Exception, 
    config: RetryConfig
) -> bool:
    """Determine if an exception should trigger a retry."""
    # Check non-retryable exceptions first
    if config.non_retryable_exceptions:
        for exc_type in config.non_retryable_exceptions:
            if isinstance(exception, exc_type):
                return False
    
    # Check retryable exceptions
    if config.retryable_exceptions:
        for exc_type in config.retryable_exceptions:
            if isinstance(exception, exc_type):
                return True
        return False  # Only retry listed exceptions
    
    # Default behavior: retry most exceptions except specific ones
    non_retryable_defaults = [
        ValueError,
        TypeError,
        AttributeError,
        NonRetryableError,
    ]
    
    for exc_type in non_retryable_defaults:
        if isinstance(exception, exc_type):
            return False
    
    return True


def retry_async(
    config: RetryConfig = None,
    circuit_breaker: CircuitBreaker = None,
    custom_delays: Optional[List[float]] = None
):
    """
    Async retry decorator with exponential backoff and circuit breaker.
    
    Args:
        config: Retry configuration
        circuit_breaker: Optional circuit breaker instance
        custom_delays: Custom delay sequence for CUSTOM strategy
    """
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            start_time = time.time()
            
            for attempt in range(1, config.max_attempts + 1):
                # Check circuit breaker
                if circuit_breaker and circuit_breaker.is_open():
                    raise RetryExhaustedError(
                        f"Circuit breaker is open after {attempt-1} attempts",
                        attempt - 1,
                        last_exception or Exception("Circuit breaker open")
                    )
                
                try:
                    # Record attempt
                    if circuit_breaker:
                        circuit_breaker.stats.total_attempts += 1
                    
                    # Execute function
                    result = await func(*args, **kwargs)
                    
                    # Record success
                    if circuit_breaker:
                        circuit_breaker.record_success()
                    
                    # Log successful retry if not first attempt
                    if attempt > 1:
                        total_time = time.time() - start_time
                        logger.info(
                            "Function succeeded after retry",
                            function=func.__name__,
                            attempt=attempt,
                            total_time_seconds=total_time
                        )
                    
                    return result
                    
                except Exception as exc:
                    last_exception = exc
                    
                    # Record failure
                    if circuit_breaker:
                        circuit_breaker.record_failure()
                    
                    # Check if exception is retryable
                    if not is_retryable_exception(exc, config):
                        logger.warning(
                            "Non-retryable exception encountered",
                            function=func.__name__,
                            exception_type=type(exc).__name__,
                            exception_message=str(exc),
                            attempt=attempt
                        )
                        raise exc
                    
                    # If this was the last attempt, raise the exception
                    if attempt >= config.max_attempts:
                        break
                    
                    # Calculate delay before next attempt
                    delay = calculate_delay(attempt, config, custom_delays)
                    
                    logger.warning(
                        "Function failed, retrying",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=config.max_attempts,
                        exception_type=type(exc).__name__,
                        exception_message=str(exc),
                        retry_delay_seconds=delay
                    )
                    
                    # Wait before next attempt
                    await asyncio.sleep(delay)
            
            # All attempts exhausted
            total_time = time.time() - start_time
            logger.error(
                "All retry attempts exhausted",
                function=func.__name__,
                max_attempts=config.max_attempts,
                total_time_seconds=total_time,
                last_exception_type=type(last_exception).__name__,
                last_exception_message=str(last_exception)
            )
            
            raise RetryExhaustedError(
                f"Function {func.__name__} failed after {config.max_attempts} attempts",
                config.max_attempts,
                last_exception
            )
        
        return wrapper
    return decorator


def retry_sync(
    config: RetryConfig = None,
    circuit_breaker: CircuitBreaker = None,
    custom_delays: Optional[List[float]] = None
):
    """
    Synchronous retry decorator with exponential backoff and circuit breaker.
    """
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            start_time = time.time()
            
            for attempt in range(1, config.max_attempts + 1):
                # Check circuit breaker
                if circuit_breaker and circuit_breaker.is_open():
                    raise RetryExhaustedError(
                        f"Circuit breaker is open after {attempt-1} attempts",
                        attempt - 1,
                        last_exception or Exception("Circuit breaker open")
                    )
                
                try:
                    # Record attempt
                    if circuit_breaker:
                        circuit_breaker.stats.total_attempts += 1
                    
                    # Execute function
                    result = func(*args, **kwargs)
                    
                    # Record success
                    if circuit_breaker:
                        circuit_breaker.record_success()
                    
                    # Log successful retry if not first attempt
                    if attempt > 1:
                        total_time = time.time() - start_time
                        logger.info(
                            "Function succeeded after retry",
                            function=func.__name__,
                            attempt=attempt,
                            total_time_seconds=total_time
                        )
                    
                    return result
                    
                except Exception as exc:
                    last_exception = exc
                    
                    # Record failure
                    if circuit_breaker:
                        circuit_breaker.record_failure()
                    
                    # Check if exception is retryable
                    if not is_retryable_exception(exc, config):
                        logger.warning(
                            "Non-retryable exception encountered",
                            function=func.__name__,
                            exception_type=type(exc).__name__,
                            exception_message=str(exc),
                            attempt=attempt
                        )
                        raise exc
                    
                    # If this was the last attempt, raise the exception
                    if attempt >= config.max_attempts:
                        break
                    
                    # Calculate delay before next attempt
                    delay = calculate_delay(attempt, config, custom_delays)
                    
                    logger.warning(
                        "Function failed, retrying",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=config.max_attempts,
                        exception_type=type(exc).__name__,
                        exception_message=str(exc),
                        retry_delay_seconds=delay
                    )
                    
                    # Wait before next attempt
                    time.sleep(delay)
            
            # All attempts exhausted
            total_time = time.time() - start_time
            logger.error(
                "All retry attempts exhausted",
                function=func.__name__,
                max_attempts=config.max_attempts,
                total_time_seconds=total_time,
                last_exception_type=type(last_exception).__name__,
                last_exception_message=str(last_exception)
            )
            
            raise RetryExhaustedError(
                f"Function {func.__name__} failed after {config.max_attempts} attempts",
                config.max_attempts,
                last_exception
            )
        
        return wrapper
    return decorator


# Pre-configured retry decorators for common scenarios
api_retry = retry_async(
    RetryConfig(
        max_attempts=3,
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
        base_delay=1.0,
        max_delay=30.0,
        retryable_exceptions=[
            ConnectionError,
            TimeoutError,
            RetryableError,
        ],
        non_retryable_exceptions=[
            ValueError,
            TypeError,
            NonRetryableError,
        ]
    )
)

database_retry = retry_async(
    RetryConfig(
        max_attempts=5,
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
        base_delay=0.5,
        max_delay=10.0,
        retryable_exceptions=[
            ConnectionError,
            TimeoutError,
        ]
    )
)

workflow_retry = retry_async(
    RetryConfig(
        max_attempts=2,
        strategy=RetryStrategy.FIXED_INTERVAL,
        base_delay=2.0,
        jitter=False,
    )
)
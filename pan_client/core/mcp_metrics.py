#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Metrics Collection for pan_client

This module provides metrics collection and tracking for MCP tool calls,
including performance statistics, error rates, and call history.
"""

import time
import threading
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class CallRecord:
    """Record of a single MCP tool call."""
    tool_name: str
    timestamp: float
    duration: float
    success: bool
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    params_count: int = 0
    result_size: int = 0


class McpMetrics:
    """Metrics collector for MCP tool calls."""
    
    def __init__(self, max_history: int = 100):
        """
        Initialize metrics collector.
        
        Args:
            max_history: Maximum number of call records to keep in history
        """
        self.max_history = max_history
        self._lock = threading.Lock()
        
        # Basic counters
        self.call_count = 0
        self.error_count = 0
        self.total_duration = 0.0
        
        # History and detailed tracking
        self.call_history: deque = deque(maxlen=max_history)
        self.tool_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'call_count': 0,
            'error_count': 0,
            'total_duration': 0.0,
            'min_duration': float('inf'),
            'max_duration': 0.0,
            'last_error': None
        })
        
        # Session tracking
        self.session_start_time = time.time()
        self.last_call_time = None
        
    def record_call(self, 
                   tool_name: str, 
                   duration: float, 
                   success: bool, 
                   error_type: Optional[str] = None,
                   error_message: Optional[str] = None,
                   params_count: int = 0,
                   result_size: int = 0) -> None:
        """
        Record a single MCP tool call.
        
        Args:
            tool_name: Name of the tool that was called
            duration: Duration of the call in seconds
            success: Whether the call was successful
            error_type: Type of error if call failed
            error_message: Error message if call failed
            params_count: Number of parameters passed
            result_size: Size of the result data
        """
        with self._lock:
            # Update global counters
            self.call_count += 1
            self.total_duration += duration
            self.last_call_time = time.time()
            
            if not success:
                self.error_count += 1
            
            # Create call record
            record = CallRecord(
                tool_name=tool_name,
                timestamp=time.time(),
                duration=duration,
                success=success,
                error_type=error_type,
                error_message=error_message,
                params_count=params_count,
                result_size=result_size
            )
            
            # Add to history
            self.call_history.append(record)
            
            # Update tool-specific stats
            tool_stat = self.tool_stats[tool_name]
            tool_stat['call_count'] += 1
            tool_stat['total_duration'] += duration
            tool_stat['min_duration'] = min(tool_stat['min_duration'], duration)
            tool_stat['max_duration'] = max(tool_stat['max_duration'], duration)
            
            if not success:
                tool_stat['error_count'] += 1
                tool_stat['last_error'] = {
                    'type': error_type,
                    'message': error_message,
                    'timestamp': time.time()
                }
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics.
        
        Returns:
            Dictionary containing various metrics and statistics
        """
        with self._lock:
            current_time = time.time()
            session_duration = current_time - self.session_start_time
            
            # Calculate rates
            calls_per_second = self.call_count / max(session_duration, 1)
            error_rate = (self.error_count / max(self.call_count, 1)) * 100
            avg_duration = self.total_duration / max(self.call_count, 1)
            
            # Recent activity (last 5 minutes)
            recent_calls = 0
            recent_errors = 0
            cutoff_time = current_time - 300  # 5 minutes ago
            
            for record in self.call_history:
                if record.timestamp >= cutoff_time:
                    recent_calls += 1
                    if not record.success:
                        recent_errors += 1
            
            # Tool breakdown
            tool_breakdown = {}
            for tool_name, stats in self.tool_stats.items():
                if stats['call_count'] > 0:
                    tool_breakdown[tool_name] = {
                        'call_count': stats['call_count'],
                        'error_count': stats['error_count'],
                        'error_rate': (stats['error_count'] / stats['call_count']) * 100,
                        'avg_duration': stats['total_duration'] / stats['call_count'],
                        'min_duration': stats['min_duration'] if stats['min_duration'] != float('inf') else 0,
                        'max_duration': stats['max_duration'],
                        'last_error': stats['last_error']
                    }
            
            return {
                # Global stats
                'call_count': self.call_count,
                'error_count': self.error_count,
                'error_rate': error_rate,
                'total_duration': self.total_duration,
                'avg_duration': avg_duration,
                'calls_per_second': calls_per_second,
                
                # Session info
                'session_duration': session_duration,
                'last_call_time': self.last_call_time,
                
                # Recent activity
                'recent_calls': recent_calls,
                'recent_errors': recent_errors,
                'recent_error_rate': (recent_errors / max(recent_calls, 1)) * 100,
                
                # Tool breakdown
                'tool_breakdown': tool_breakdown,
                
                # Health indicators
                'is_healthy': error_rate < 10 and recent_calls > 0,
                'health_score': max(0, 100 - error_rate - (recent_errors * 2))
            }
    
    def get_recent_calls(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent call records.
        
        Args:
            limit: Maximum number of recent calls to return
            
        Returns:
            List of recent call records as dictionaries
        """
        with self._lock:
            recent = list(self.call_history)[-limit:]
            return [
                {
                    'tool_name': record.tool_name,
                    'timestamp': record.timestamp,
                    'duration': record.duration,
                    'success': record.success,
                    'error_type': record.error_type,
                    'error_message': record.error_message,
                    'params_count': record.params_count,
                    'result_size': record.result_size
                }
                for record in recent
            ]
    
    def get_tool_stats(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a specific tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool statistics or None if tool not found
        """
        with self._lock:
            if tool_name not in self.tool_stats:
                return None
            
            stats = self.tool_stats[tool_name]
            if stats['call_count'] == 0:
                return None
            
            return {
                'call_count': stats['call_count'],
                'error_count': stats['error_count'],
                'error_rate': (stats['error_count'] / stats['call_count']) * 100,
                'total_duration': stats['total_duration'],
                'avg_duration': stats['total_duration'] / stats['call_count'],
                'min_duration': stats['min_duration'] if stats['min_duration'] != float('inf') else 0,
                'max_duration': stats['max_duration'],
                'last_error': stats['last_error']
            }
    
    def reset(self) -> None:
        """Reset all metrics to initial state."""
        with self._lock:
            self.call_count = 0
            self.error_count = 0
            self.total_duration = 0.0
            self.call_history.clear()
            self.tool_stats.clear()
            self.session_start_time = time.time()
            self.last_call_time = None
    
    def get_summary(self) -> str:
        """
        Get a human-readable summary of metrics.
        
        Returns:
            String summary of current metrics
        """
        stats = self.get_stats()
        
        if stats['call_count'] == 0:
            return "No MCP calls recorded"
        
        return (
            f"Calls: {stats['call_count']} | "
            f"Errors: {stats['error_count']} ({stats['error_rate']:.1f}%) | "
            f"Avg: {stats['avg_duration']:.3f}s | "
            f"Health: {stats['health_score']:.0f}%"
        )

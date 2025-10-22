import asyncio
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from collections import Counter
from difflib import SequenceMatcher
import json
from loguru import logger

@dataclass
class CodeFragment:
    content: str
    model: str
    confidence: float
    language: Optional[str] = None
    syntax_valid: bool = True
    
class CodeSynthesizer:
    def __init__(self):
        self.voting_weights = {
            'devstral:latest': 1.2,
            'qwen2.5-coder:14b': 1.15,
            'codestral:latest': 1.1,
            'mistral-small:24b': 1.05,
            'deepseek-coder:latest': 1.1,
            'granite-code:8b': 1.0,
            'stable-code:3b': 0.9,
            'codegemma:7b-instruct': 1.0
        }
        
    async def merge_responses(self, subtask_results: List[Dict], original_prompt: str) -> Dict:
        # Collect models for logging
        models = []
        for result in subtask_results:
            for response in result.get('responses', []):
                if response.get('model') not in models:
                    models.append(response.get('model'))
        
        # Log to console
        if models:
            logger.info(f"🔧 Synthesizing code from {len(models)} models: {', '.join(models)}")
        
        # Also log to terminal if available
        try:
            import streamlit as st
            if hasattr(st.session_state, 'terminal'):
                from ..ui.terminal import GenerationLogger
                term_logger = GenerationLogger(st.session_state.terminal)
                term_logger.log_synthesis(models)
        except:
            pass
        
        all_fragments = []
        
        for result in subtask_results:
            for response in result.get('responses', []):
                fragment = CodeFragment(
                    content=response['response'],
                    model=response['model'],
                    confidence=self._calculate_confidence(response)
                )
                all_fragments.append(fragment)
                
        if not all_fragments:
            return {
                'code': '',
                'confidence': 0,
                'explanations': ['No valid responses received']
            }
            
        code_blocks = self._extract_code_blocks(all_fragments)
        
        if len(code_blocks) == 1:
            return {
                'code': code_blocks[0]['code'],
                'confidence': code_blocks[0]['confidence'],
                'explanations': []
            }
            
        consensus_code = await self._build_consensus(code_blocks)
        validated = await self._validate_syntax(consensus_code)
        
        # Log to console
        consensus_pct = validated['confidence'] if validated else 0
        logger.info(f"📊 Consensus achieved: {consensus_pct:.1%} confidence")
        
        # Also log to terminal if available
        try:
            import streamlit as st
            if hasattr(st.session_state, 'terminal'):
                from ..ui.terminal import GenerationLogger
                term_logger = GenerationLogger(st.session_state.terminal)
                term_logger.log_synthesis([f['model'] for f in all_fragments], consensus_pct)
        except:
            pass
        
        return {
            'code': validated['code'],
            'confidence': validated['confidence'],
            'explanations': validated.get('fixes', [])
        }
        
    def _extract_code_blocks(self, fragments: List[CodeFragment]) -> List[Dict]:
        code_blocks = []
        
        for fragment in fragments:
            code_pattern = r'```(?:python|py|javascript|js|java|cpp|c\+\+|rust|go)?\n(.*?)```'
            matches = re.findall(code_pattern, fragment.content, re.DOTALL)
            
            if matches:
                for match in matches:
                    code_blocks.append({
                        'code': match.strip(),
                        'model': fragment.model,
                        'confidence': fragment.confidence
                    })
            else:
                lines = fragment.content.strip().split('\n')
                code_lines = [l for l in lines if not l.startswith('#') or l.startswith('#!')]
                if code_lines:
                    code_blocks.append({
                        'code': '\n'.join(code_lines),
                        'model': fragment.model,
                        'confidence': fragment.confidence * 0.8
                    })
                    
        return code_blocks
        
    async def _build_consensus(self, code_blocks: List[Dict]) -> str:
        if not code_blocks:
            return ""
            
        similarity_groups = self._group_similar_code(code_blocks)
        
        best_group = max(similarity_groups, key=lambda g: sum(
            self.voting_weights.get(block['model'], 1.0) * block['confidence']
            for block in g
        ))
        
        if len(best_group) == 1:
            return best_group[0]['code']
            
        merged = await self._merge_similar_blocks(best_group)
        return merged
        
    def _group_similar_code(self, code_blocks: List[Dict]) -> List[List[Dict]]:
        groups = []
        used = set()
        
        for i, block1 in enumerate(code_blocks):
            if i in used:
                continue
                
            group = [block1]
            used.add(i)
            
            for j, block2 in enumerate(code_blocks[i+1:], i+1):
                if j in used:
                    continue
                    
                similarity = SequenceMatcher(
                    None,
                    block1['code'],
                    block2['code']
                ).ratio()
                
                if similarity > 0.7:
                    group.append(block2)
                    used.add(j)
                    
            groups.append(group)
            
        return groups
        
    async def _merge_similar_blocks(self, blocks: List[Dict]) -> str:
        lines_votes = {}
        max_lines = max(len(b['code'].split('\n')) for b in blocks)
        
        for line_idx in range(max_lines):
            line_candidates = []
            
            for block in blocks:
                lines = block['code'].split('\n')
                if line_idx < len(lines):
                    weight = self.voting_weights.get(block['model'], 1.0)
                    line_candidates.append((lines[line_idx], weight))
                    
            if line_candidates:
                line_counter = Counter()
                for line, weight in line_candidates:
                    line_counter[line] += weight
                    
                best_line = line_counter.most_common(1)[0][0]
                lines_votes[line_idx] = best_line
                
        merged_lines = [lines_votes[i] for i in sorted(lines_votes.keys())]
        return '\n'.join(merged_lines)
        
    async def _validate_syntax(self, code: str) -> Dict:
        validation_results = {
            'code': code,
            'confidence': 1.0,
            'fixes': []
        }
        
        try:
            compile(code, '<string>', 'exec')
            validation_results['syntax_valid'] = True
        except SyntaxError as e:
            validation_results['syntax_valid'] = False
            validation_results['confidence'] *= 0.7
            
            fixed = await self._attempt_syntax_fix(code, str(e))
            if fixed != code:
                validation_results['code'] = fixed
                validation_results['fixes'].append(f"Fixed syntax error: {e}")
                
        return validation_results
        
    async def _attempt_syntax_fix(self, code: str, error: str) -> str:
        lines = code.split('\n')
        
        if 'unexpected indent' in error:
            fixed_lines = []
            base_indent = 0
            for line in lines:
                if line.strip():
                    current_indent = len(line) - len(line.lstrip())
                    if current_indent % 4 != 0:
                        current_indent = (current_indent // 4) * 4
                    fixed_lines.append(' ' * current_indent + line.lstrip())
                else:
                    fixed_lines.append(line)
            return '\n'.join(fixed_lines)
            
        if 'invalid syntax' in error and ':' in error:
            for i, line in enumerate(lines):
                if line.strip() and not line.strip().startswith('#'):
                    if any(kw in line for kw in ['def ', 'class ', 'if ', 'for ', 'while ', 'try:', 'except']):
                        if not line.rstrip().endswith(':'):
                            lines[i] = line.rstrip() + ':'
            return '\n'.join(lines)
            
        return code
        
    def _calculate_confidence(self, response: Dict) -> float:
        base_confidence = 0.5
        
        if 'tokens' in response:
            if response['tokens'] > 100:
                base_confidence += 0.1
            if response['tokens'] > 500:
                base_confidence += 0.1
                
        model_weight = self.voting_weights.get(response['model'], 1.0)
        return min(base_confidence * model_weight, 1.0)
        
    async def enhance_with_comments(self, code: str, explanation_model: str = "llama3.1:latest") -> str:
        from ..models.ollama_manager import OllamaLoadBalancer
        import os
        
        hosts = [os.getenv('OLLAMA_HOST', 'http://localhost:11434')]
        lb = OllamaLoadBalancer(hosts)
        
        enhance_prompt = f"""Add helpful inline comments to this code. Keep the code identical, only add comments.

Code:
{code}

Return the code with added comments."""

        response = await lb.generate(
            model=explanation_model,
            prompt=enhance_prompt,
            temperature=0.3
        )
        
        return response['response']
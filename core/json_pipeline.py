"""
JSON Pipeline for standardizing all model outputs
Forces JSON extraction, validation, and correction
"""

import json
import re
import asyncio
from typing import Dict, Any, Optional, Type, List, Union
from pydantic import BaseModel, Field, create_model, ValidationError, validator
from pydantic.fields import FieldInfo
from loguru import logger
from enum import Enum
from datetime import datetime

class ResponseType(Enum):
    """Types of responses we expect"""
    CODE = "code"
    EXPLANATION = "explanation"
    ANALYSIS = "analysis"
    SYNTHESIS = "synthesis"
    TOOL_CALL = "tool_call"
    STRUCTURED_DATA = "structured_data"
    ERROR = "error"

class BaseResponseSchema(BaseModel):
    """Base schema all responses inherit from"""
    response_type: ResponseType
    timestamp: datetime = Field(default_factory=datetime.now)
    model: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class CodeResponseSchema(BaseResponseSchema):
    """Schema for code generation responses"""
    response_type: ResponseType = ResponseType.CODE
    code: str
    language: str = "python"
    explanation: Optional[str] = None
    imports: List[str] = Field(default_factory=list)
    functions: List[str] = Field(default_factory=list)
    classes: List[str] = Field(default_factory=list)

class ExplanationResponseSchema(BaseResponseSchema):
    """Schema for explanation responses"""
    response_type: ResponseType = ResponseType.EXPLANATION
    explanation: str
    key_points: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)

class AnalysisResponseSchema(BaseResponseSchema):
    """Schema for analysis responses"""
    response_type: ResponseType = ResponseType.ANALYSIS
    analysis: str
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    metrics: Dict[str, Union[int, float]] = Field(default_factory=dict)

class ToolCallSchema(BaseResponseSchema):
    """Schema for tool calls"""
    response_type: ResponseType = ResponseType.TOOL_CALL
    tool_name: str
    arguments: Dict[str, Any]
    expected_output: Optional[str] = None

class JSONExtractor:
    """Extract JSON from various response formats"""
    
    @staticmethod
    def extract_json(text: str) -> Optional[Dict]:
        """Force extract JSON from text"""
        if not text:
            return None
            
        # Try direct JSON parsing first
        try:
            return json.loads(text)
        except:
            pass
        
        # Try to find JSON blocks in markdown
        json_patterns = [
            r'```json\s*([\s\S]*?)```',
            r'```\s*([\s\S]*?)```',
            r'\{[\s\S]*\}',
            r'\[[\s\S]*\]'
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.MULTILINE | re.DOTALL)
            for match in matches:
                try:
                    # Clean up the match
                    cleaned = match.strip()
                    # Try to parse
                    data = json.loads(cleaned)
                    if isinstance(data, (dict, list)):
                        return data
                except:
                    continue
        
        # Try to extract key-value pairs from text
        try:
            # Look for patterns like "key: value" or "key = value"
            lines = text.split('\n')
            extracted = {}
            
            for line in lines:
                # Skip empty lines
                if not line.strip():
                    continue
                    
                # Try colon separator
                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        key = parts[0].strip().strip('"').strip("'")
                        value = parts[1].strip().strip('"').strip("'")
                        
                        # Try to convert value to appropriate type
                        if value.lower() in ['true', 'false']:
                            value = value.lower() == 'true'
                        elif value.isdigit():
                            value = int(value)
                        elif value.replace('.', '').isdigit():
                            value = float(value)
                            
                        extracted[key] = value
                        
                # Try equals separator
                elif '=' in line:
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        key = parts[0].strip().strip('"').strip("'")
                        value = parts[1].strip().strip('"').strip("'")
                        
                        if value.lower() in ['true', 'false']:
                            value = value.lower() == 'true'
                        elif value.isdigit():
                            value = int(value)
                        elif value.replace('.', '').isdigit():
                            value = float(value)
                            
                        extracted[key] = value
            
            if extracted:
                return extracted
                
        except Exception as e:
            logger.debug(f"Failed to extract key-value pairs: {e}")
        
        # Last resort: try to build JSON from common patterns
        return JSONExtractor._build_json_from_text(text)
    
    @staticmethod
    def _build_json_from_text(text: str) -> Optional[Dict]:
        """Build JSON from unstructured text"""
        result = {}
        
        # Check for code blocks
        code_pattern = r'```(?:python|py|javascript|js|java|cpp|c\+\+|rust|go)?\s*\n(.*?)```'
        code_matches = re.findall(code_pattern, text, re.DOTALL)
        if code_matches:
            result['code'] = code_matches[0].strip()
            result['response_type'] = ResponseType.CODE.value
            
            # Extract language
            lang_match = re.search(r'```(\w+)', text)
            if lang_match:
                result['language'] = lang_match.group(1)
            else:
                result['language'] = 'python'  # Default language
        
        # Check for lists (bullet points or numbered)
        list_pattern = r'(?:^|\n)\s*[\-\*\•]\s+(.+)'
        list_items = re.findall(list_pattern, text, re.MULTILINE)
        if list_items:
            result['items'] = list_items
            
        # Check for numbered lists
        numbered_pattern = r'(?:^|\n)\s*\d+\.\s+(.+)'
        numbered_items = re.findall(numbered_pattern, text, re.MULTILINE)
        if numbered_items:
            result['numbered_items'] = numbered_items
        
        # If we have some content, add the full text
        if result:
            result['raw_text'] = text
            return result
            
        # If nothing else works, return wrapped text
        return {
            'response_type': 'text',
            'content': text
        }

class SchemaGenerator:
    """Dynamically generate Pydantic schemas based on context"""
    
    @staticmethod
    def generate_schema(prompt: str, context: Dict[str, Any]) -> Type[BaseModel]:
        """Generate appropriate schema based on prompt and context"""
        
        # Detect response type from prompt
        prompt_lower = prompt.lower()
        
        if any(word in prompt_lower for word in ['code', 'function', 'class', 'implement', 'write']):
            return CodeResponseSchema
            
        elif any(word in prompt_lower for word in ['explain', 'describe', 'what', 'how', 'why']):
            return ExplanationResponseSchema
            
        elif any(word in prompt_lower for word in ['analyze', 'review', 'evaluate', 'assess']):
            return AnalysisResponseSchema
            
        elif 'tool' in context or 'function_call' in context:
            return ToolCallSchema
            
        else:
            # Generate custom schema based on context
            return SchemaGenerator._create_dynamic_schema(context)
    
    @staticmethod
    def _create_dynamic_schema(context: Dict[str, Any]) -> Type[BaseModel]:
        """Create a dynamic schema from context"""
        fields = {
            'response_type': (ResponseType, ResponseType.STRUCTURED_DATA),
            'timestamp': (datetime, Field(default_factory=datetime.now)),
        }
        
        # Add fields based on context
        if 'expected_fields' in context:
            for field_name, field_type in context['expected_fields'].items():
                if isinstance(field_type, str):
                    # Convert string type hints to actual types
                    type_map = {
                        'str': str,
                        'int': int,
                        'float': float,
                        'bool': bool,
                        'list': List[Any],
                        'dict': Dict[str, Any]
                    }
                    field_type = type_map.get(field_type, str)
                    
                fields[field_name] = (field_type, Field(...))
        else:
            # Default fields for generic response
            fields.update({
                'content': (str, Field(...)),
                'metadata': (Dict[str, Any], Field(default_factory=dict))
            })
        
        return create_model('DynamicResponseSchema', **fields, __base__=BaseResponseSchema)

class JSONPipeline:
    """Main pipeline for JSON standardization"""
    
    def __init__(self, load_balancer=None):
        self.lb = load_balancer
        self.extractor = JSONExtractor()
        self.generator = SchemaGenerator()
        self.correction_model = "llama3.2:latest"
        self.max_retries = 3
        
    async def process(self, 
                     response: str, 
                     prompt: str = "",
                     context: Dict[str, Any] = None,
                     schema: Optional[Type[BaseModel]] = None) -> Dict[str, Any]:
        """Process response through JSON pipeline"""
        
        context = context or {}
        
        # Log processing start
        logger.info(f"🔄 Processing response through JSON pipeline")
        
        # Step 1: Extract JSON from response
        extracted = self.extractor.extract_json(response)
        
        if not extracted:
            logger.warning("Failed to extract JSON, using fallback")
            extracted = {'raw_response': response}
        
        # Step 2: Generate or use provided schema
        if not schema:
            schema = self.generator.generate_schema(prompt, context)
            logger.debug(f"Generated schema: {schema.__name__}")
        
        # Step 3: Validate and correct
        validated_data = await self._validate_and_correct(
            extracted, 
            schema, 
            prompt, 
            response
        )
        
        return validated_data
    
    async def _validate_and_correct(self, 
                                   data: Dict, 
                                   schema: Type[BaseModel], 
                                   original_prompt: str,
                                   original_response: str) -> Dict[str, Any]:
        """Validate data against schema and correct if needed"""
        
        for attempt in range(self.max_retries):
            try:
                # Try to validate
                validated = schema(**data)
                logger.success(f"✅ Validation passed on attempt {attempt + 1}")
                return validated.model_dump()
                
            except ValidationError as e:
                logger.warning(f"❌ Validation failed on attempt {attempt + 1}: {e}")
                
                if attempt < self.max_retries - 1 and self.lb:
                    # Use llama3.2:latest to correct the schema
                    data = await self._correct_with_model(
                        data,
                        schema,
                        e,
                        original_prompt,
                        original_response
                    )
                else:
                    # Final attempt - try to fix common issues
                    data = self._apply_fallback_fixes(data, schema, e)
        
        # If all retries failed, return best effort
        logger.error("All validation attempts failed, returning best effort")
        return self._create_best_effort_response(data, schema)
    
    async def _correct_with_model(self,
                                 data: Dict,
                                 schema: Type[BaseModel],
                                 error: ValidationError,
                                 original_prompt: str,
                                 original_response: str) -> Dict:
        """Use llama3.2:latest to correct the data"""
        
        correction_prompt = f"""You are a JSON correction assistant. Fix the following JSON to match the required schema.

Original User Prompt: {original_prompt}

Original Model Response: {original_response[:500]}...

Current JSON Data:
{json.dumps(data, indent=2)}

Required Schema:
{self._schema_to_description(schema)}

Validation Errors:
{str(error)}

Please provide the corrected JSON that matches the schema exactly. Return ONLY valid JSON, no explanations.
"""
        
        try:
            # Call llama3.2:latest for correction
            logger.info(f"🔧 Using {self.correction_model} for correction")
            
            response = await self.lb.generate(
                model=self.correction_model,
                prompt=correction_prompt,
                temperature=0.3  # Low temperature for consistency
            )
            
            # Extract JSON from correction response
            corrected = self.extractor.extract_json(response['response'])
            
            if corrected:
                logger.info("📝 Received correction from model")
                return corrected
            else:
                logger.warning("Failed to extract JSON from correction")
                return data
                
        except Exception as e:
            logger.error(f"Correction failed: {e}")
            return data
    
    def _schema_to_description(self, schema: Type[BaseModel]) -> str:
        """Convert Pydantic schema to readable description"""
        fields = []
        
        for field_name, field_info in schema.model_fields.items():
            field_type = field_info.annotation
            required = field_info.is_required()
            default = field_info.default
            
            field_desc = f"- {field_name}: {field_type.__name__ if hasattr(field_type, '__name__') else str(field_type)}"
            
            if required:
                field_desc += " (required)"
            elif default is not None:
                field_desc += f" (default: {default})"
                
            fields.append(field_desc)
        
        return "Fields:\n" + "\n".join(fields)
    
    def _apply_fallback_fixes(self, data: Dict, schema: Type[BaseModel], error: ValidationError) -> Dict:
        """Apply common fixes for validation errors"""
        
        # Get field requirements from schema
        for error_item in error.errors():
            field = error_item['loc'][0] if error_item['loc'] else None
            error_type = error_item['type']
            
            if not field:
                continue
                
            if error_type == 'missing':
                # Add missing required fields with defaults
                field_info = schema.model_fields.get(field)
                if field_info:
                    if field_info.default is not None:
                        data[field] = field_info.default
                    elif hasattr(field_info, 'default_factory') and field_info.default_factory:
                        data[field] = field_info.default_factory()
                    else:
                        # Guess default based on type
                        field_type = field_info.annotation
                        if field_type == str:
                            data[field] = ""
                        elif field_type == int:
                            data[field] = 0
                        elif field_type == float:
                            data[field] = 0.0
                        elif field_type == bool:
                            data[field] = False
                        elif field_type == list or 'List' in str(field_type):
                            data[field] = []
                        elif field_type == dict or 'Dict' in str(field_type):
                            data[field] = {}
                        else:
                            data[field] = None
                            
            elif error_type == 'type_error' or error_type == 'string_type':
                # Try to convert to correct type
                field_info = schema.model_fields.get(field)
                if field_info and field in data:
                    try:
                        field_type = field_info.annotation
                        if field_type == str:
                            data[field] = str(data[field])
                        elif field_type == int:
                            data[field] = int(data[field])
                        elif field_type == float:
                            data[field] = float(data[field])
                        elif field_type == bool:
                            data[field] = bool(data[field])
                    except:
                        pass
        
        return data
    
    def _create_best_effort_response(self, data: Dict, schema: Type[BaseModel]) -> Dict:
        """Create best effort response when validation fails"""
        
        result = {}
        
        # Copy valid fields
        for field_name, field_info in schema.model_fields.items():
            if field_name in data:
                result[field_name] = data[field_name]
            elif field_info.default is not None:
                result[field_name] = field_info.default
            elif hasattr(field_info, 'default_factory') and field_info.default_factory:
                result[field_name] = field_info.default_factory()
            else:
                # Set to None or empty
                field_type = field_info.annotation
                if field_type == str:
                    result[field_name] = ""
                elif field_type in [int, float]:
                    result[field_name] = 0
                elif field_type == bool:
                    result[field_name] = False
                elif 'List' in str(field_type):
                    result[field_name] = []
                elif 'Dict' in str(field_type):
                    result[field_name] = {}
                else:
                    result[field_name] = None
        
        # Add any extra data to metadata if available
        if 'metadata' in result:
            for key, value in data.items():
                if key not in result:
                    result['metadata'][key] = value
        
        return result

class StreamingJSONPipeline(JSONPipeline):
    """JSON pipeline with streaming support"""
    
    async def process_stream(self,
                            response_stream,
                            prompt: str = "",
                            context: Dict[str, Any] = None,
                            schema: Optional[Type[BaseModel]] = None):
        """Process streaming response through JSON pipeline"""
        
        # Collect full response from stream
        full_response = ""
        async for chunk in response_stream:
            if isinstance(chunk, dict) and 'chunk' in chunk:
                full_response += chunk['chunk']
            elif isinstance(chunk, str):
                full_response += chunk
                
            # Yield progress updates
            yield {
                'status': 'collecting',
                'chars_collected': len(full_response)
            }
        
        # Process collected response
        result = await self.process(full_response, prompt, context, schema)
        
        yield {
            'status': 'complete',
            'result': result
        }

# Utility functions
def extract_code_blocks(text: str) -> List[Dict[str, str]]:
    """Extract all code blocks from text"""
    pattern = r'```(?P<lang>\w+)?\n(?P<code>.*?)```'
    matches = re.finditer(pattern, text, re.DOTALL)
    
    blocks = []
    for match in matches:
        blocks.append({
            'language': match.group('lang') or 'unknown',
            'code': match.group('code').strip()
        })
    
    return blocks

def sanitize_json_string(text: str) -> str:
    """Sanitize text for JSON parsing"""
    # Remove control characters
    text = re.sub(r'[\x00-\x1f\x7f]', '', text)
    # Escape quotes properly
    text = text.replace('\\', '\\\\').replace('"', '\\"')
    return text
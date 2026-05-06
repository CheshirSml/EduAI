"""
Валидатор заданий: проверка объёма, структуры, оформления.
"""
import re
from typing import Dict, List, Any
from datetime import datetime
import hashlib

from config.settings import settings
from utils.logger import get_logger
from modules.homework.checker.file_parser import parse_assignment_file

logger = get_logger(__name__)


class AssignmentValidator:
    """Валидатор студенческих работ."""
    
    # Паттерны для поиска разделов (регистронезависимые)
    REQUIRED_SECTIONS_PATTERNS = {
        'введение': r'\b(введение|introduction)\b',
        'анализ': r'\b(анализ|analysis|основн[ая|ое]|main\s+body)\b',
        'вывод': r'\b(вывод|conclusion|заключ[еи]ние)\b',
        'литератур': r'\b(литератур|список\s+источник|reference|bibliography)\b'
    }
    
    # Паттерн APA-цитирования: (Фамилия, год) или (Author, year)
    APA_CITATION_PATTERN = r'\([А-ЯA-Z][а-яa-zёЁ]+,\s*\d{4}\)'
    
    def __init__(self):
        self.settings = settings
    
    def _compute_hash(self, text: str) -> str:
        """SHA256 хэш первых 4KB текста."""
        return hashlib.sha256(text[:4096].encode('utf-8')).hexdigest()
    
    def _parse_requirements_from_spec(self, spec_md: str) -> dict:
        """
        Извлекает ключевые требования из Markdown-спецификации.
        
        Поддерживаемые паттерны:
        - "1500±10% слов" / "1500 слов (±10%)" → {"word_limit": (1350, 1650)}
        - "минимум 3 научных статьи" / "не менее 3 источников" → {"min_citations": 3}
        - "оформление по APA" / "стиль APA 7" → {"requires_apa": True}
        - "- Введение", "## Структура:\n- Введение" → {"required_sections": [...]}
        
        Returns:
            Dict с извлечёнными требованиями
        """
        requirements = {
            'word_limit': None,  # (min, max)
            'min_citations': None,
            'requires_apa': False,
            'required_sections': []
        }
        
        # Парсинг лимита слов
        # Паттерны: "1500±10% слов", "1500 слов (±10%)", "1500-2000 слов"
        word_patterns = [
            r'(\d+)\s*[±+-]\s*(\d+)%?\s*слов',  # 1500±10% слов
            r'(\d+)\s*слов\s*\(?\s*[±+-]\s*(\d+)%?\)?',  # 1500 слов (±10%)
            r'(\d+)\s*[-–—]\s*(\d+)\s*слов',  # 1500-2000 слов
        ]
        
        for pattern in word_patterns:
            match = re.search(pattern, spec_md, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    try:
                        base = int(groups[0])
                        second = int(groups[1])
                        
                        # Если второе число маленькое (< 100), это процент
                        if second < 100:
                            tolerance = second
                            min_words = int(base * (1 - tolerance / 100))
                            max_words = int(base * (1 + tolerance / 100))
                        else:
                            # Это диапазон
                            min_words = min(base, second)
                            max_words = max(base, second)
                        
                        requirements['word_limit'] = (min_words, max_words)
                        break
                    except ValueError:
                        continue
        
        # Парсинг требований к цитированию
        citation_patterns = [
            r'(?:минимум|не\s+менее)\s+(\d+)\s*(?:научн|статей|источник|цитат)',
            r'(\d+)\s*(?:научн|статей|источник|цитат)\s*(?:минимум|не\s+менее)',
        ]
        
        for pattern in citation_patterns:
            match = re.search(pattern, spec_md, re.IGNORECASE)
            if match:
                try:
                    requirements['min_citations'] = int(match.group(1))
                    break
                except (ValueError, IndexError):
                    continue
        
        # Проверка на APA
        if re.search(r'\bAPA\s*(?:7|6)?\b', spec_md, re.IGNORECASE):
            requirements['requires_apa'] = True
        
        # Парсинг обязательных разделов
        # Ищем списки после "Структура" или "Разделы"
        section_headers = re.findall(
            r'(?:##?\s*структура|##?\s*раздел|должен\s+содержать)[:\s]*\n([\s\S]*?)(?=\n##|\Z)',
            spec_md,
            re.IGNORECASE
        )
        
        for header_content in section_headers:
            # Извлекаем пункты списка
            sections = re.findall(r'[-•*]\s*([А-ЯA-Z][^\n]+)', header_content)
            requirements['required_sections'].extend(sections)
        
        # Если не найдено в структуре, ищем явные упоминания
        if not requirements['required_sections']:
            for section_name in ['введение', 'анализ', 'вывод', 'заключение']:
                if re.search(rf'\b{section_name}\b', spec_md, re.IGNORECASE):
                    requirements['required_sections'].append(section_name.capitalize())
        
        return requirements
    
    def validate(
        self,
        file_relative_path: str,
        discipline: str,
        spec_text: str | None = None
    ) -> dict:
        """
        Быстрая пред-проверка файла: объём, структура, оформление.
        
        Args:
            file_relative_path: Путь относительно ASSIGNMENTS_ROOT
            discipline: Идентификатор дисциплины
            spec_text: Текст спецификации (опционально, загрузится автоматически если не указан)
        
        Returns:
            Dict с результатами валидации
        """
        issues: List[str] = []
        
        try:
            # Парсинг файла
            parse_result = parse_assignment_file(file_relative_path)
        except FileNotFoundError as e:
            logger.error("file_not_found", path=file_relative_path)
            return {
                "word_count": 0,
                "issues": [f"⚠️ Файл не найден: {file_relative_path}"],
                "is_valid": False,
                "checked_at": datetime.now().isoformat(),
                "file_hash": ""
            }
        except ValueError as e:
            logger.error("parse_error", path=file_relative_path, error=str(e))
            return {
                "word_count": 0,
                "issues": [f"⚠️ Ошибка парсинга: {str(e)}"],
                "is_valid": False,
                "checked_at": datetime.now().isoformat(),
                "file_hash": ""
            }
        
        text = parse_result['text']
        word_count = parse_result['word_count']
        file_hash = parse_result['file_hash']
        
        # Загрузка спецификации если не передана
        if not spec_text:
            from modules.homework.mcp_server import get_assignment_spec
            try:
                spec_text = get_assignment_spec(discipline)
            except Exception as e:
                logger.warning("spec_load_failed", discipline=discipline, error=str(e))
                spec_text = ""
        
        # Извлечение требований
        requirements = self._parse_requirements_from_spec(spec_text)
        
        # 1. Проверка объёма
        if requirements['word_limit']:
            min_words, max_words = requirements['word_limit']
            if word_count < min_words or word_count > max_words:
                issues.append(
                    f"⚠️ Объём: {word_count} слов "
                    f"(требуется {min_words}–{max_words} по спецификации)"
                )
            else:
                issues.append(f"✅ Объём: {word_count} слов (в пределах нормы)")
        else:
            issues.append(f"ℹ️ Объём: {word_count} слов (требование не указано)")
        
        # 2. Проверка структуры
        found_sections = []
        missing_sections = []
        
        for section_pattern in self.REQUIRED_SECTIONS_PATTERNS:
            pattern = self.REQUIRED_SECTIONS_PATTERNS[section_pattern]
            if re.search(pattern, text, re.IGNORECASE):
                found_sections.append(section_pattern)
            else:
                missing_sections.append(section_pattern)
        
        if missing_sections:
            issues.append(f"⚠️ Структура: отсутствуют разделы: {', '.join(missing_sections)}")
        elif found_sections:
            issues.append(f"✅ Структура: все обязательные разделы присутствуют")
        else:
            issues.append("ℹ️ Структура: не удалось определить разделы")
        
        # 3. Проверка цитирования (если требуется APA)
        if requirements['requires_apa']:
            apa_citations = re.findall(self.APA_CITATION_PATTERN, text)
            min_citations = requirements.get('min_citations', 3)
            
            if len(apa_citations) < min_citations:
                issues.append(
                    f"⚠️ Цитирование: найдено {len(apa_citations)} ссылок в формате APA, "
                    f"требуется минимум {min_citations}"
                )
            else:
                issues.append(f"✅ Цитирование: {len(apa_citations)} ссылок в формате APA")
        elif requirements['min_citations']:
            # Просто подсчёт цитат в любом формате
            min_citations = requirements['min_citations']
            # Грубый подсчёт: ищем цифры в скобках (год)
            citation_candidates = re.findall(r'\([^)]*\d{4}[^)]*\)', text)
            
            if len(citation_candidates) < min_citations:
                issues.append(
                    f"⚠️ Источники: найдено {len(citation_candidates)} цитат, "
                    f"требуется минимум {min_citations}"
                )
            else:
                issues.append(f"✅ Источники: {len(citation_candidates)} цитат")
        
        # Определение валидности (критические ошибки только если файл не найден)
        is_valid = len([i for i in issues if i.startswith("⚠️")]) == 0
        
        return {
            "word_count": word_count,
            "issues": issues,
            "is_valid": is_valid,
            "checked_at": datetime.now().isoformat(),
            "file_hash": file_hash
        }


def validate_assignment_format(file_relative_path: str, discipline: str) -> dict:
    """
    Утилита для валидации формата задания.
    
    Args:
        file_relative_path: Относительный путь от ASSIGNMENTS_ROOT
        discipline: Идентификатор дисциплины
    
    Returns:
        Dict с результатами валидации
    """
    validator = AssignmentValidator()
    return validator.validate(file_relative_path, discipline)

"""
Парсинг локальных файлов: DOCX, PDF, TXT → текст.
"""
import hashlib
from pathlib import Path
from typing import Tuple, Optional
import chardet

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FileParser:
    """Парсер файлов различных форматов."""
    
    SUPPORTED_EXTENSIONS = {'.txt', '.docx', '.pdf'}
    
    @staticmethod
    def _compute_file_hash(file_path: Path) -> str:
        """Вычисляет SHA256 хэш первых 4KB файла."""
        with open(file_path, 'rb') as f:
            return hashlib.sha256(f.read(4096)).hexdigest()
    
    @staticmethod
    def _check_file_size(file_path: Path) -> Tuple[bool, int]:
        """
        Проверка размера файла.
        
        Returns:
            (is_valid, size_bytes): Кортеж с результатом проверки и размером
        """
        size_bytes = file_path.stat().st_size
        max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        return size_bytes <= max_size_bytes, size_bytes
    
    def parse_file(self, file_path: Path) -> dict:
        """
        Парсинг файла в текст.
        
        Args:
            file_path: Путь к файлу
        
        Returns:
            Dict с результатами:
            {
                "text": str,              # Извлечённый текст
                "word_count": int,        # Количество слов
                "file_hash": str,         # Хэш файла
                "file_size_bytes": int,   # Размер файла
                "extension": str,         # Расширение файла
                "issues": List[str]       # Предупреждения при парсинге
            }
        
        Raises:
            FileNotFoundError: Если файл не найден
            ValueError: Если формат не поддерживается или файл слишком большой
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        
        extension = file_path.suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Неподдерживаемый формат: {extension}. "
                f"Поддерживаются: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )
        
        # Проверка размера
        is_valid_size, file_size = self._check_file_size(file_path)
        if not is_valid_size:
            raise ValueError(
                f"Файл слишком большой: {file_size / (1024*1024):.2f} МБ. "
                f"Максимум: {settings.MAX_FILE_SIZE_MB} МБ"
            )
        
        issues = []
        text = ""
        
        try:
            if extension == '.txt':
                text = self._parse_txt(file_path)
            elif extension == '.docx':
                text = self._parse_docx(file_path)
            elif extension == '.pdf':
                text = self._parse_pdf(file_path)
        except Exception as e:
            logger.error("parse_error", file_path=str(file_path), error=str(e))
            issues.append(f"⚠️ Ошибка при парсинге: {str(e)}")
        
        # Подсчёт слов (русскоязычный подсчёт)
        word_count = len(text.split())
        
        return {
            "text": text,
            "word_count": word_count,
            "file_hash": self._compute_file_hash(file_path),
            "file_size_bytes": file_size,
            "extension": extension,
            "issues": issues
        }
    
    def _parse_txt(self, file_path: Path) -> str:
        """Парсинг TXT файла с авто-определением кодировки."""
        with open(file_path, 'rb') as f:
            raw_data = f.read()
        
        # Определение кодировки
        detected = chardet.detect(raw_data)
        encoding = detected['encoding'] or 'utf-8'
        confidence = detected.get('confidence', 0)
        
        if confidence < 0.7:
            logger.warning("low_encoding_confidence", file=str(file_path), encoding=encoding, confidence=confidence)
        
        try:
            text = raw_data.decode(encoding)
        except UnicodeDecodeError:
            # Fallback на utf-8 с заменой ошибок
            text = raw_data.decode('utf-8', errors='replace')
            logger.warning("decode_fallback", file=str(file_path))
        
        return text.strip()
    
    def _parse_docx(self, file_path: Path) -> str:
        """Парсинг DOCX файла."""
        try:
            from docx import Document
        except ImportError:
            raise ImportError("Установите python-docx: pip install python-docx")
        
        try:
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return '\n'.join(paragraphs)
        except Exception as e:
            logger.error("docx_parse_error", file=str(file_path), error=str(e))
            raise ValueError(f"Ошибка чтения DOCX: {e}")
    
    def _parse_pdf(self, file_path: Path) -> str:
        """Парсинг PDF файла."""
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise ImportError("Установите PyPDF2: pip install PyPDF2")
        
        try:
            reader = PdfReader(file_path)
            pages = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages.append(text)
            
            if not pages:
                logger.warning("pdf_empty_text", file=str(file_path))
                return ""
            
            return '\n'.join(pages)
        except Exception as e:
            logger.error("pdf_parse_error", file=str(file_path), error=str(e))
            raise ValueError(f"Ошибка чтения PDF: {e}")


def parse_assignment_file(file_relative_path: str) -> dict:
    """
    Утилита для парсинга файла задания.
    
    Args:
        file_relative_path: Относительный путь от ASSIGNMENTS_ROOT
    
    Returns:
        Dict с результатами парсинга
    
    Raises:
        FileNotFoundError, ValueError
    """
    parser = FileParser()
    full_path = settings.ASSIGNMENTS_ROOT / file_relative_path
    return parser.parse_file(full_path)

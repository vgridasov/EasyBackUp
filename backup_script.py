#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт резервного копирования файлов из домашней папки пользователя
Поддерживает macOS, Linux и Windows
"""

import os
import sys
import zipfile
import shutil
import platform
import psutil
from datetime import datetime
from pathlib import Path
import subprocess
from typing import List, Tuple, Optional

class BackupManager:
    def __init__(self):
        self.system = platform.system()
        self.home_dir = Path.home()
        self.username = os.getlogin()
        self.extensions = self._load_extensions()
        self.blacklist = self._load_blacklist()
        
    def _load_extensions(self) -> List[str]:
        """Загружает список расширений из файла"""
        try:
            with open('file_extensions.txt', 'r', encoding='utf-8') as f:
                extensions = []
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and line.startswith('.'):
                        extensions.append(line.lower())
                return extensions
        except FileNotFoundError:
            print("❌ Файл file_extensions.txt не найден!")
            return []
    
    def _load_blacklist(self) -> List[str]:
        """Загружает черный список папок и файлов из файла"""
        try:
            with open('blacklist.txt', 'r', encoding='utf-8') as f:
                blacklist = []
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        blacklist.append(line.lower())
                return blacklist
        except FileNotFoundError:
            print("⚠️  Файл blacklist.txt не найден, исключения не применяются")
            return []
    
    def _is_blacklisted(self, name: str) -> bool:
        """Проверяет, находится ли файл или папка в черном списке"""
        name_lower = name.lower()
        
        # Проверяем точные совпадения
        if name_lower in self.blacklist:
            return True
            
        # Проверяем шаблоны с wildcards
        for pattern in self.blacklist:
            if '*' in pattern:
                import fnmatch
                if fnmatch.fnmatch(name_lower, pattern):
                    return True
            elif name_lower.startswith(pattern.rstrip('*')):
                return True
                
        return False
    
    def find_files_to_backup(self) -> List[Path]:
        """Находит все файлы для резервного копирования"""
        files_to_backup = []
        print(f"🔍 Поиск файлов в {self.home_dir}...")
        
        try:
            for root, dirs, files in os.walk(self.home_dir):
                # Фильтруем папки с учетом blacklist
                dirs[:] = [d for d in dirs if not self._is_blacklisted(d)]
                
                for file in files:
                    # Проверяем файл на blacklist
                    if self._is_blacklisted(file):
                        continue
                        
                    file_path = Path(root) / file
                    if file_path.suffix.lower() in self.extensions:
                        files_to_backup.append(file_path)
                        
                if len(files_to_backup) % 1000 == 0 and len(files_to_backup) > 0:
                    print(f"   Найдено файлов: {len(files_to_backup)}")
                    
        except PermissionError as e:
            print(f"⚠️  Нет доступа к некоторым папкам: {e}")
        
        return files_to_backup
    
    def calculate_total_size(self, files: List[Path]) -> int:
        """Подсчитывает общий размер файлов"""
        total_size = 0
        print("📊 Подсчет общего размера файлов...")
        
        for i, file_path in enumerate(files):
            try:
                total_size += file_path.stat().st_size
                if i % 500 == 0:
                    print(f"   Обработано: {i}/{len(files)} файлов")
            except (OSError, FileNotFoundError):
                continue
                
        return total_size
    
    def format_size(self, size_bytes: int) -> str:
        """Форматирует размер в человеко-читаемый вид"""
        for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} ПБ"
    
    def find_external_drives(self) -> List[Tuple[str, int, int]]:
        """Находит подключенные внешние накопители"""
        external_drives = []
        
        for partition in psutil.disk_partitions():
            if 'removable' in partition.opts or (self.system == "Darwin" and 
                                               '/Volumes/' in partition.mountpoint and 
                                               partition.mountpoint != '/'):
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    external_drives.append((
                        partition.mountpoint,
                        usage.free,
                        usage.total
                    ))
                except PermissionError:
                    continue
                    
        return external_drives
    
    def select_compression_level(self) -> int:
        """Позволяет пользователю выбрать уровень сжатия"""
        print("\n🗜️  Выберите режим сжатия:")
        print("1. Быстрый (без сжатия)")
        print("2. Обычный (средний)")
        print("3. Максимальный (медленный, но компактный)")
        
        while True:
            try:
                choice = input("Введите номер (1-3): ").strip()
                if choice == '1':
                    return zipfile.ZIP_STORED
                elif choice == '2':
                    return zipfile.ZIP_DEFLATED
                elif choice == '3':
                    return zipfile.ZIP_LZMA
                else:
                    print("❌ Введите число от 1 до 3")
            except KeyboardInterrupt:
                print("\n❌ Операция отменена пользователем")
                sys.exit(1)
    
    def create_backup_filename(self, drive_path: str) -> str:
        """Создает имя файла архива"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{self.username}_{timestamp}.zip"
        return os.path.join(drive_path, filename)
    
    def create_backup_archive(self, files: List[Path], output_path: str, 
                            compression: int) -> bool:
        """Создает архив с резервной копией"""
        print(f"\n📦 Создание архива: {output_path}")
        
        try:
            with zipfile.ZipFile(output_path, 'w', compression=compression) as zipf:
                total_files = len(files)
                
                for i, file_path in enumerate(files):
                    try:
                        # Создаем относительный путь от домашней папки
                        relative_path = file_path.relative_to(self.home_dir)
                        zipf.write(file_path, relative_path)
                        
                        if i % 100 == 0:
                            progress = (i / total_files) * 100
                            print(f"   Прогресс: {progress:.1f}% ({i}/{total_files})")
                            
                    except (OSError, FileNotFoundError) as e:
                        print(f"⚠️  Ошибка при добавлении {file_path}: {e}")
                        continue
                    except KeyboardInterrupt:
                        print("\n❌ Операция отменена пользователем")
                        return False
                        
                print("✅ Архив успешно создан!")
                return True
                
        except Exception as e:
            print(f"❌ Ошибка при создании архива: {e}")
            return False
    
    def run_backup(self):
        """Основная функция запуска резервного копирования"""
        print("🚀 Запуск резервного копирования EasyBackUp")
        print("=" * 50)
        
        # Проверяем наличие файла расширений
        if not self.extensions:
            print("❌ Не удалось загрузить список расширений файлов")
            return
        
        print(f"📁 Домашняя папка: {self.home_dir}")
        print(f"👤 Пользователь: {self.username}")
        print(f"💾 Операционная система: {self.system}")
        print(f"📋 Загружено расширений: {len(self.extensions)}")
        print(f"🚫 Исключений в blacklist: {len(self.blacklist)}")
        
        # Поиск файлов для резервного копирования
        files_to_backup = self.find_files_to_backup()
        if not files_to_backup:
            print("❌ Файлы для резервного копирования не найдены")
            return
            
        print(f"✅ Найдено файлов: {len(files_to_backup)}")
        
        # Подсчет общего размера
        total_size = self.calculate_total_size(files_to_backup)
        formatted_size = self.format_size(total_size)
        print(f"📊 Общий размер: {formatted_size}")
        
        # Поиск внешних накопителей
        external_drives = self.find_external_drives()
        if not external_drives:
            print("❌ Внешние накопители не найдены")
            return
            
        print("\n💾 Найденные внешние накопители:")
        for i, (path, free, total) in enumerate(external_drives, 1):
            free_formatted = self.format_size(free)
            total_formatted = self.format_size(total)
            print(f"   {i}. {path} (свободно: {free_formatted} из {total_formatted})")
        
        # Выбор накопителя
        while True:
            try:
                choice = input(f"\nВыберите накопитель (1-{len(external_drives)}): ").strip()
                drive_idx = int(choice) - 1
                if 0 <= drive_idx < len(external_drives):
                    selected_drive, free_space, _ = external_drives[drive_idx]
                    break
                else:
                    print(f"❌ Введите число от 1 до {len(external_drives)}")
            except (ValueError, KeyboardInterrupt):
                print("\n❌ Операция отменена")
                return
        
        # Проверка свободного места
        if free_space < total_size:
            print(f"❌ Недостаточно места на накопителе!")
            print(f"   Требуется: {self.format_size(total_size)}")
            print(f"   Доступно: {self.format_size(free_space)}")
            return
        
        print(f"✅ Места достаточно (доступно: {self.format_size(free_space)})")
        
        # Выбор уровня сжатия
        compression = self.select_compression_level()
        
        # Создание имени файла архива
        backup_path = self.create_backup_filename(selected_drive)
        
        # Подтверждение операции
        print(f"\n📋 Сводка операции:")
        print(f"   Файлов к копированию: {len(files_to_backup)}")
        print(f"   Общий размер: {formatted_size}")
        print(f"   Место назначения: {backup_path}")
        
        confirm = input("\nНачать резервное копирование? (y/N): ").strip().lower()
        if confirm not in ['y', 'yes', 'д', 'да']:
            print("❌ Операция отменена")
            return
        
        # Создание архива
        success = self.create_backup_archive(files_to_backup, backup_path, compression)
        
        if success:
            final_size = Path(backup_path).stat().st_size
            print(f"\n🎉 Резервное копирование завершено успешно!")
            print(f"📁 Архив сохранен: {backup_path}")
            print(f"📊 Размер архива: {self.format_size(final_size)}")
            print(f"📈 Коэффициент сжатия: {((total_size - final_size) / total_size * 100):.1f}%")
        else:
            print("\n❌ Резервное копирование не удалось")

def main():
    try:
        backup_manager = BackupManager()
        backup_manager.run_backup()
    except KeyboardInterrupt:
        print("\n❌ Операция прервана пользователем")
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

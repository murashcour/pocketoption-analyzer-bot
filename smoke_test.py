#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke-тест analyzer_bot.py через ast.

Проверяет:
1. Все вызовы (Call) ссылаются на имена, которые определены:
   - в модуле (def/class)
   - импортированы
   - являются встроенными (builtins)
   - параметрами функций
   - локальными переменными

Не панацея — но ловит 'висячие' вызовы типа _find_signal_for_step_3.

Запуск:  python3 smoke_test.py
"""

import ast
import builtins
import sys
from pathlib import Path

FILE = Path("analyzer_bot.py")
if not FILE.exists():
    print(f"❌ Файл {FILE} не найден")
    sys.exit(1)

src = FILE.read_text(encoding="utf-8")
tree = ast.parse(src)

# === 1. Собираем все определённые имена на уровне модуля ===
module_names = set()

for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
        module_names.add(node.name)
    elif isinstance(node, ast.ClassDef):
        module_names.add(node.name)
    elif isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                module_names.add(t.id)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        module_names.add(node.target.id)
    elif isinstance(node, ast.Import):
        for alias in node.names:
            module_names.add(alias.asname or alias.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            module_names.add(alias.asname or alias.name)

# Встроенные имена
builtin_names = set(dir(builtins))
# Добавим частые глобалы
module_names.update({
    "__name__", "__file__", "__doc__", "__builtins__",
})

# === 2. Собираем все Call-узлы ===
# Для каждого Call берём имя вызываемого: Name(id=...) или Attribute(...)
calls = []   # (lineno, name)

for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            calls.append((node.lineno, func.id))
        elif isinstance(func, ast.Attribute):
            # x.method() — игнорируем, т.к. методы объектов
            pass

# === 3. Собираем локальные имена (параметры, локальные переменные) ===
# Сложно точно — упростим: собираем все Assign/For/With/Except/comprehension
local_names = set()

for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        # параметры
        for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
            local_names.add(arg.arg)
        if node.args.vararg:
            local_names.add(node.args.vararg.arg)
        if node.args.kwarg:
            local_names.add(node.args.kwarg.arg)
    elif isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                local_names.add(t.id)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        local_names.add(node.target.id)
    elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
        local_names.add(node.target.id)
    elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
        local_names.add(node.target.id)
    elif isinstance(node, ast.With):
        for item in node.items:
            if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                local_names.add(item.optional_vars.id)
    elif isinstance(node, ast.ExceptHandler) and node.name:
        local_names.add(node.name)
    elif isinstance(node, ast.comprehension) and isinstance(node.target, ast.Name):
        local_names.add(node.target.id)

# === 4. Сверяем ===
defined = module_names | local_names | builtin_names

unknown_calls = []
for lineno, name in calls:
    if name not in defined:
        unknown_calls.append((lineno, name))

# === 5. Отчёт ===
print(f"📄 Файл: {FILE}")
print(f"   Всего строк: {len(src.splitlines())}")
print(f"   Определено имён (module): {len(module_names)}")
print(f"   Локальных имён: {len(local_names)}")
print(f"   Всего Call-узлов: {len(calls)}")
print()

if unknown_calls:
    print(f"⚠ Найдено {len(unknown_calls)} вызовов неизвестных имён:")
    for lineno, name in unknown_calls:
        print(f"   строка {lineno}: {name}()")
    print()
    print("ВНИМАНИЕ: возможен NameError при выполнении.")
    print("Проверь каждое имя вручную — возможно, это метод объекта,")
    print("который ast не смог отследить, или действительно баг.")
    sys.exit(2)
else:
    print("✅ Все Call-узлы ссылаются на известные имена.")
    print("   Модуль должен импортироваться без NameError.")
    sys.exit(0)

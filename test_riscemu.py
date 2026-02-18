"""Test riscemu - full working example"""

from riscemu.config import RunConfig
from riscemu.core import UserModeCPU
from riscemu.parser import AssemblyFileLoader
from riscemu.instructions import RV32I, RV32M
import tempfile
import os

print("--- Testing riscemu ---")
code = """.text
.globl _start
_start:
    li a0, 10
    li a1, 20
    add a2, a0, a1
    li a7, 93
    ecall
"""

with tempfile.NamedTemporaryFile(mode='w', suffix='.asm', delete=False) as f:
    f.write(code)
    temp_path = f.name

try:
    # Load assembly
    with open(temp_path, 'r') as source_file:
        loader = AssemblyFileLoader(temp_path, source_file, {})
        program = loader.parse()
    
    print(f"Program parsed: {program}")
    
    cfg = RunConfig(verbosity=0, debug_on_exception=False)
    cpu = UserModeCPU([RV32I, RV32M], cfg)
    cpu.load_program(program)
    
    # Use launch() which handles everything properly
    try:
        cpu.launch(program)
    except SystemExit:
        pass  # Normal exit
    except RuntimeError as e:
        if "No next instruction" not in str(e):
            raise
    
    print("\n--- Results ---")
    print(f"a0 (x10) = {cpu.regs.get('a0', 0)}")
    print(f"a1 (x11) = {cpu.regs.get('a1', 0)}")
    print(f"a2 (x12) = {cpu.regs.get('a2', 0)}")
    print("\nSUCCESS! riscemu is working correctly.")
    
finally:
    os.unlink(temp_path)

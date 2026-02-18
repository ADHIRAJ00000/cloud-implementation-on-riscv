import io
import sys
import re
import random
from contextlib import redirect_stdout, redirect_stderr


def strip_ansi(text):
    """Remove ANSI escape codes from text."""
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_pattern.sub('', text)


class RISCVEmulator:
    """
    RISC-V Emulator wrapper for cloud simulation.
    Uses riscemu library to execute RISC-V assembly code.
    """
    
    def __init__(self, node_id, memory_mb=512):
        self.node_id = node_id
        self.memory_mb = memory_mb
        self.registers = {f'x{i}': 0 for i in range(32)}
        self.registers['x0'] = 0  # x0 is always 0
        self.pc = 0
        self.memory = {}
    
    def execute(self, assembly_code):
        """
        Execute RISC-V assembly code and return output.
        First tries riscemu library, falls back to built-in emulator.
        """
        # Try riscemu first
        try:
            result = self._execute_with_riscemu(assembly_code)
            return {
                'success': True,
                'output': '[riscemu] ' + result['output'],
                'registers': result['registers'],
                'error': ''
            }
        except ImportError as e:
            # riscemu not installed, use fallback
            riscemu_error = f"riscemu import error: {e}"
        except Exception as e:
            # riscemu failed, try fallback
            import traceback
            riscemu_error = f"riscemu error: {e}\n{traceback.format_exc()}"
        
        # Fallback to built-in emulator
        try:
            result = self._execute_simple(assembly_code)
            result['output'] = f'[built-in emulator] (riscemu failed: {riscemu_error})\n' + result['output']
            return result
        except Exception as e:
            return {
                'success': False,
                'output': '',
                'registers': self.registers,
                'error': str(e)
            }
    
    def _execute_with_riscemu(self, assembly_code):
        """Execute using riscemu library."""
        from riscemu.config import RunConfig
        from riscemu.core import UserModeCPU
        from riscemu.parser import AssemblyFileLoader
        from riscemu.instructions import RV32I, RV32M
        import tempfile
        import os
        
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        # Write assembly to temp file (riscemu needs a file)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.asm', delete=False) as f:
            # Add minimal program structure if not present
            code = assembly_code.strip()
            if '.text' not in code and '.globl' not in code:
                code = f".text\n.globl _start\n_start:\n{code}\n    li a7, 93\n    ecall"
            f.write(code)
            temp_path = f.name
        
        try:
            # Load the assembly file (need to open as file object)
            with open(temp_path, 'r') as source_file:
                loader = AssemblyFileLoader(temp_path, source_file, {})
                program = loader.parse()
            
            cfg = RunConfig(verbosity=0, debug_on_exception=False)
            cpu = UserModeCPU([RV32I, RV32M], cfg)
            cpu.load_program(program)
            
            # Use launch() or run() with exception handling
            cycles = 0
            max_cycles = 10000
            
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                try:
                    # Try using run() which handles exit syscall properly
                    cpu.launch(program)
                except SystemExit:
                    # Normal exit via ecall
                    pass
                except RuntimeError as e:
                    if "No next instruction" not in str(e):
                        raise
                    # Program ended without explicit exit - that's ok
            
            # Get register values - use ABI names for better readability
            abi_names = ['zero', 'ra', 'sp', 'gp', 'tp', 't0', 't1', 't2',
                        's0', 's1', 'a0', 'a1', 'a2', 'a3', 'a4', 'a5',
                        'a6', 'a7', 's2', 's3', 's4', 's5', 's6', 's7',
                        's8', 's9', 's10', 's11', 't3', 't4', 't5', 't6']
            
            registers = {}
            output_lines = ["Program executed successfully", "", "--- Register State ---"]
            
            for i in range(32):
                try:
                    # Try different ways to get register value
                    val = cpu.regs.get(abi_names[i], None)
                    if val is None:
                        val = cpu.regs.get(f'x{i}', 0)
                    # Convert to int (handles Int32 type)
                    val = int(val) if val else 0
                    registers[f'x{i}'] = val
                    if val != 0:
                        output_lines.append(f"x{i} ({abi_names[i]}) = {val}")
                except Exception as e:
                    registers[f'x{i}'] = 0
            
            # Add any stdout from the program (strip ANSI codes)
            program_output = strip_ansi(stdout_capture.getvalue())
            if program_output:
                output_lines.insert(1, program_output)
            
            return {
                'output': '\n'.join(output_lines),
                'registers': registers
            }
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except:
                pass
    
    def _execute_simple(self, assembly_code):
        """
        Simple built-in RISC-V emulator for basic instructions.
        Supports: add, sub, addi, li, mv, and basic arithmetic.
        """
        lines = assembly_code.strip().split('\n')
        output_lines = []
        self.registers = {f'x{i}': 0 for i in range(32)}
        
        # Register aliases
        aliases = {
            'zero': 'x0', 'ra': 'x1', 'sp': 'x2', 'gp': 'x3',
            'tp': 'x4', 't0': 'x5', 't1': 'x6', 't2': 'x7',
            's0': 'x8', 'fp': 'x8', 's1': 'x9',
            'a0': 'x10', 'a1': 'x11', 'a2': 'x12', 'a3': 'x13',
            'a4': 'x14', 'a5': 'x15', 'a6': 'x16', 'a7': 'x17',
            's2': 'x18', 's3': 'x19', 's4': 'x20', 's5': 'x21',
            's6': 'x22', 's7': 'x23', 's8': 'x24', 's9': 'x25',
            's10': 'x26', 's11': 'x27',
            't3': 'x28', 't4': 'x29', 't5': 'x30', 't6': 'x31'
        }
        
        def get_reg(name):
            name = name.strip().lower()
            if name in aliases:
                name = aliases[name]
            return name
        
        def get_value(operand):
            operand = operand.strip()
            if operand.startswith('x') or operand in aliases:
                reg = get_reg(operand)
                return self.registers.get(reg, 0)
            return int(operand, 0)
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('.') or line.endswith(':'):
                continue
            
            # Remove comments
            if '#' in line:
                line = line.split('#')[0].strip()
            
            parts = line.replace(',', ' ').split()
            if not parts:
                continue
                
            instr = parts[0].lower()
            
            try:
                if instr == 'li':  # Load immediate
                    rd = get_reg(parts[1])
                    imm = int(parts[2], 0)
                    if rd != 'x0':
                        self.registers[rd] = imm
                    output_lines.append(f"li {rd}, {imm} -> {rd}={imm}")
                    
                elif instr == 'mv':  # Move
                    rd = get_reg(parts[1])
                    rs = get_reg(parts[2])
                    if rd != 'x0':
                        self.registers[rd] = self.registers.get(rs, 0)
                    output_lines.append(f"mv {rd}, {rs} -> {rd}={self.registers[rd]}")
                    
                elif instr == 'add':
                    rd = get_reg(parts[1])
                    rs1 = get_reg(parts[2])
                    rs2 = get_reg(parts[3])
                    result = self.registers.get(rs1, 0) + self.registers.get(rs2, 0)
                    if rd != 'x0':
                        self.registers[rd] = result
                    output_lines.append(f"add {rd}, {rs1}, {rs2} -> {rd}={result}")
                    
                elif instr == 'sub':
                    rd = get_reg(parts[1])
                    rs1 = get_reg(parts[2])
                    rs2 = get_reg(parts[3])
                    result = self.registers.get(rs1, 0) - self.registers.get(rs2, 0)
                    if rd != 'x0':
                        self.registers[rd] = result
                    output_lines.append(f"sub {rd}, {rs1}, {rs2} -> {rd}={result}")
                    
                elif instr == 'addi':
                    rd = get_reg(parts[1])
                    rs1 = get_reg(parts[2])
                    imm = int(parts[3], 0)
                    result = self.registers.get(rs1, 0) + imm
                    if rd != 'x0':
                        self.registers[rd] = result
                    output_lines.append(f"addi {rd}, {rs1}, {imm} -> {rd}={result}")
                    
                elif instr == 'mul':
                    rd = get_reg(parts[1])
                    rs1 = get_reg(parts[2])
                    rs2 = get_reg(parts[3])
                    result = self.registers.get(rs1, 0) * self.registers.get(rs2, 0)
                    if rd != 'x0':
                        self.registers[rd] = result
                    output_lines.append(f"mul {rd}, {rs1}, {rs2} -> {rd}={result}")
                    
                elif instr in ['and', 'or', 'xor']:
                    rd = get_reg(parts[1])
                    rs1 = get_reg(parts[2])
                    rs2 = get_reg(parts[3])
                    v1 = self.registers.get(rs1, 0)
                    v2 = self.registers.get(rs2, 0)
                    if instr == 'and':
                        result = v1 & v2
                    elif instr == 'or':
                        result = v1 | v2
                    else:
                        result = v1 ^ v2
                    if rd != 'x0':
                        self.registers[rd] = result
                    output_lines.append(f"{instr} {rd}, {rs1}, {rs2} -> {rd}={result}")
                    
                elif instr == 'sll':  # Shift left logical
                    rd = get_reg(parts[1])
                    rs1 = get_reg(parts[2])
                    rs2 = get_reg(parts[3])
                    result = self.registers.get(rs1, 0) << (self.registers.get(rs2, 0) & 0x1f)
                    if rd != 'x0':
                        self.registers[rd] = result
                    output_lines.append(f"sll {rd}, {rs1}, {rs2} -> {rd}={result}")
                    
                elif instr == 'srl':  # Shift right logical
                    rd = get_reg(parts[1])
                    rs1 = get_reg(parts[2])
                    rs2 = get_reg(parts[3])
                    result = self.registers.get(rs1, 0) >> (self.registers.get(rs2, 0) & 0x1f)
                    if rd != 'x0':
                        self.registers[rd] = result
                    output_lines.append(f"srl {rd}, {rs1}, {rs2} -> {rd}={result}")
                    
                elif instr in ['nop', 'ecall', 'ebreak']:
                    output_lines.append(f"{instr} executed")
                    
                else:
                    output_lines.append(f"Unknown instruction: {instr}")
                    
            except Exception as e:
                output_lines.append(f"Error executing '{line}': {str(e)}")
        
        # Show final register state (non-zero registers)
        output_lines.append("\n--- Final Register State ---")
        for reg, val in self.registers.items():
            if val != 0:
                output_lines.append(f"{reg} = {val}")
        
        return {
            'success': True,
            'output': '\n'.join(output_lines),
            'registers': self.registers,
            'error': ''
        }


def simulate_cpu_usage():
    """Get real CPU usage from system."""
    try:
        import psutil
        return psutil.cpu_percent(interval=0.1)
    except:
        return random.randint(10, 95)


def simulate_memory_usage(total_mb):
    """Get real memory usage from system, scaled to node's allocated memory."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        # Scale actual usage percentage to node's allocated memory
        usage_percent = mem.percent / 100
        return int(total_mb * usage_percent)
    except:
        return random.randint(50, int(total_mb * 0.8))


def get_system_info():
    """Get real system information."""
    try:
        import psutil
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            'cpu_cores': cpu_count,
            'cpu_freq_mhz': int(cpu_freq.current) if cpu_freq else 0,
            'total_memory_mb': int(mem.total / (1024 * 1024)),
            'used_memory_mb': int(mem.used / (1024 * 1024)),
            'memory_percent': mem.percent,
            'total_disk_gb': int(disk.total / (1024 * 1024 * 1024)),
            'used_disk_gb': int(disk.used / (1024 * 1024 * 1024)),
            'disk_percent': disk.percent
        }
    except:
        return None

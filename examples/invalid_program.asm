# Deliberately broken program: shows syntax/semantic error reporting.
ADD R1, R2 R3          # missing comma
LW R4, 0(R2            # missing ')'
FOO R1, R2, R3         # unknown instruction
ADDI R1, R2, R3        # register where a number is expected
BEQ R1, R2, nowhere    # undefined label
SUB R40, R1, R2        # register out of range
loop: loop2: NOP       # two labels on one line
@

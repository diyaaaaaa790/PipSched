# Classic load-use hazards: every LW is consumed by the very next instruction.
LW  R1, 0(R2)
ADD R3, R1, R4
LW  R5, 4(R2)
SUB R6, R5, R4
LW  R7, 8(R2)
AND R8, R7, R3
OR  R9, R6, R8
SW  R9, 12(R2)


all: border_timing.tap

clean:
	rm -f border_timing.bas.tap border_timing.asm.tap border_timing.tap

border_timing.tap: border_timing.bas border_timing.asm
	bas2tap -q -a border_timing.bas border_timing.bas.tap
	pasmo --tap border_timing.asm border_timing.asm.tap
	cat border_timing.bas.tap border_timing.asm.tap >border_timing.tap
	rm border_timing.bas.tap border_timing.asm.tap

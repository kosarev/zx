
all: screen_timing.tap

clean:
	rm -f screen_timing.bas.tap screen_timing.asm.tap screen_timing.tap

screen_timing.tap: screen_timing.bas screen_timing.asm generate_drawing.py
	python3 generate_drawing.py >drawing.inc
	bas2tap -q -a screen_timing.bas screen_timing.bas.tap
	pasmo --tap screen_timing.asm screen_timing.asm.tap
	cat screen_timing.bas.tap screen_timing.asm.tap >screen_timing.tap
	rm screen_timing.bas.tap screen_timing.asm.tap

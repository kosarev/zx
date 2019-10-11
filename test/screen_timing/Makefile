
all: screen_timing_early.tap screen_timing_late.tap

clean:
	rm -f screen_timing.bas.tap screen_timing.asm.tap screen_timing.tap

screen_timing_early.tap: screen_timing.bas screen_timing.asm generate_drawing.py
	python3 generate_drawing.py >drawing_early.inc
	bas2tap -q -a screen_timing.bas screen_timing_early.bas.tap
	cpp -P -w screen_timing.asm >screen_timing_early.asm
	pasmo --tap screen_timing_early.asm screen_timing_early.asm.tap
	cat screen_timing_early.bas.tap screen_timing_early.asm.tap >screen_timing_early.tap
	rm screen_timing_early.bas.tap screen_timing_early.asm.tap screen_timing_early.asm

screen_timing_late.tap: screen_timing.bas screen_timing.asm generate_drawing.py
	python3 generate_drawing.py late_timings >drawing_late.inc
	bas2tap -q -a screen_timing.bas screen_timing_late.bas.tap
	cpp -P -w -DLATE_TIMINGS screen_timing.asm >screen_timing_late.asm
	pasmo --tap screen_timing_late.asm screen_timing_late.asm.tap
	cat screen_timing_late.bas.tap screen_timing_late.asm.tap >screen_timing_late.tap
	rm screen_timing_late.bas.tap screen_timing_late.asm.tap screen_timing_late.asm

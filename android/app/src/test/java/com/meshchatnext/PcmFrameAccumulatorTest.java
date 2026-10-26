package com.meshchatnext;

import org.junit.Test;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import static org.junit.Assert.*;

public class PcmFrameAccumulatorTest {

    @Test
    public void frameSizesMatchTelephoneProfiles() {
        int[] durations = {10, 20, 60, 200, 320, 400};

        for (int ms : durations) {
            PcmFrameAccumulator accumulator =
                new PcmFrameAccumulator(48000, ms);

            assertEquals(ms * 96, accumulator.getFrameBytes());
        }
    }

    @Test
    public void partialReadsProduceCompleteFrames() {
        PcmFrameAccumulator accumulator =
            new PcmFrameAccumulator(48000, 20);

        List<byte[]> frames = new ArrayList<>();
        byte[] input = new byte[4096];

        for (int i = 0; i < input.length; i++) {
            input[i] = (byte) (i % 251);
        }

        accumulator.append(input, input.length, frames::add);

        assertEquals(2, frames.size());
        assertArrayEquals(
            Arrays.copyOfRange(input, 0, 1920),
            frames.get(0)
        );
        assertArrayEquals(
            Arrays.copyOfRange(input, 1920, 3840),
            frames.get(1)
        );

        byte[] remainder = new byte[1664];
        Arrays.fill(remainder, (byte) 7);

        accumulator.append(remainder, remainder.length, frames::add);

        assertEquals(3, frames.size());

        byte[] expected = new byte[1920];
        System.arraycopy(input, 3840, expected, 0, 256);
        System.arraycopy(remainder, 0, expected, 256, 1664);

        assertArrayEquals(expected, frames.get(2));
    }

    @Test
    public void resetDiscardsPreviousCallAudio() {
        PcmFrameAccumulator accumulator =
            new PcmFrameAccumulator(48000, 10);

        List<byte[]> frames = new ArrayList<>();

        byte[] oldAudio = new byte[480];
        Arrays.fill(oldAudio, (byte) 1);
        accumulator.append(oldAudio, oldAudio.length, frames::add);

        accumulator.reset();

        byte[] newAudio = new byte[960];
        Arrays.fill(newAudio, (byte) 2);
        accumulator.append(newAudio, newAudio.length, frames::add);

        assertEquals(1, frames.size());
        assertArrayEquals(newAudio, frames.get(0));
    }

    @Test
    public void rejectsInvalidPcmConfiguration() {
        try {
            new PcmFrameAccumulator(48000, 0);
            fail("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            // Correct.
        }
    }

    @Test
    public void rejectsOddLengthPcm() {
        PcmFrameAccumulator accumulator =
            new PcmFrameAccumulator(48000, 20);

        try {
            accumulator.append(new byte[3], 3, frame -> {});
            fail("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            // Correct.
        }
    }
}

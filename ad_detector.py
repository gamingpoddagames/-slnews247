"""Conservative automated advertisement *candidate* detection for authorized footage.

Black-frame transitions and silence are not proof of an advertisement. This module
writes a JSON review report; it never deletes content or covers source watermarks.
"""
import json
import re
import subprocess
from pathlib import Path

BLACK = re.compile(r'black_start:(\d+(?:\.\d+)?)\s+black_end:(\d+(?:\.\d+)?)')
SILENCE_START = re.compile(r'silence_start:\s*(\d+(?:\.\d+)?)')
SILENCE_END = re.compile(r'silence_end:\s*(\d+(?:\.\d+)?)')


def parse_breaks(stderr):
    black = [(float(a), float(b)) for a, b in BLACK.findall(stderr)]
    silent = []
    start = None
    for line in stderr.splitlines():
        match = SILENCE_START.search(line)
        if match:
            start = float(match.group(1))
        match = SILENCE_END.search(line)
        if match and start is not None:
            end = float(match.group(1))
            if end > start:
                silent.append((start, end))
            start = None
    return black, silent


def candidate_intervals(duration, black, silent):
    """Flag edge segments separated by a black transition plus nearby silence.

    Signals can also appear in legitimate news footage, so every result is
    review-required, never an automatic deletion instruction.
    """
    if not 4 <= duration <= 7200:
        return []
    candidates = []
    for start, end in black:
        midpoint = (start + end) / 2
        nearby = any(abs((s0 + s1) / 2 - midpoint) <= 2 for s0, s1 in silent)
        if not nearby:
            continue
        if 5 <= midpoint <= min(duration * .25, 60):
            candidates.append({'start': 0.0, 'end': round(midpoint, 2),
                               'reason': 'intro near black and silence transition',
                               'status': 'review_required'})
        elif max(duration * .75, duration - 60) <= midpoint <= duration - 5:
            candidates.append({'start': round(midpoint, 2), 'end': round(duration, 2),
                               'reason': 'outro near black and silence transition',
                               'status': 'review_required'})
    # Keep reports modest; both edges can be ambiguous.
    unique = {}
    for item in candidates:
        unique[(item['start'], item['end'])] = item
    return list(unique.values())[:4]


def detect_ad_candidates(video_path, output_path):
    from video import probe_footage
    duration = probe_footage(str(video_path))['duration']
    cmd = ['ffmpeg', '-hide_banner', '-nostats', '-i', str(video_path),
           '-vf', 'blackdetect=d=0.25:pix_th=0.10',
           '-af', 'silencedetect=noise=-35dB:d=0.25',
           '-f', 'null', '-']
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=150, check=False)
    if result.returncode:
        raise RuntimeError('Video/audio analysis failed; leave footage unchanged')
    black, silent = parse_breaks(result.stderr)
    report = {'source': str(video_path), 'duration_seconds': duration,
              'black_intervals': black, 'silence_intervals': silent,
              'candidates': candidate_intervals(duration, black, silent),
              'automatic_cut': False, 'source_watermark_modified': False,
              'instruction': 'Review candidates. Mark ad_segments and ad_segments_reviewed=true only after verifying cuts.'}
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('input_video')
    parser.add_argument('--report', default='output/ad_review.json')
    args = parser.parse_args()
    print(json.dumps(detect_ad_candidates(args.input_video, args.report), indent=2))

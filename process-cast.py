#!/usr/bin/env python3
"""
Process asciinema .cast file for Remotion rendering.
Extracts frame-by-frame terminal state at 30fps.
"""

import json
import sys
import os

def process_cast(cast_path: str, output_path: str, fps: int = 30):
    """Parse .cast file and generate frame data for Remotion."""
    
    with open(cast_path, 'r') as f:
        lines = f.read().strip().split('\n')
    
    # Parse header
    header = json.loads(lines[0])
    width = header.get('width', 120)
    height = header.get('height', 40)
    
    # Parse events
    events = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = json.loads(line)
        if len(parts) >= 3 and parts[1] == 'o':
            events.append({
                'time': parts[0],
                'text': parts[2],
            })
    
    if not events:
        print("No events found in .cast file")
        return
    
    total_duration = events[-1]['time']
    total_frames = int(total_duration * fps) + 1
    
    print(f"Cast info: {width}x{height}, {total_duration:.1f}s, {len(events)} events, {total_frames} frames")
    
    # Generate frame data: for each frame, compute the terminal state
    frames = []
    event_idx = 0
    terminal_text = ""
    
    for frame_num in range(total_frames):
        t = frame_num / fps
        
        # Process all events up to this frame's time
        while event_idx < len(events) and events[event_idx]['time'] <= t:
            terminal_text += events[event_idx]['text']
            event_idx += 1
        
        # Truncate to reasonable size for Remotion
        # Keep last N lines that fit the terminal height
        lines_list = terminal_text.split('\n')
        if len(lines_list) > height:
            lines_list = lines_list[-height:]
        
        frames.append({
            'frame': frame_num,
            'time': round(t, 3),
            'text': '\n'.join(lines_list),
            'progress': round(event_idx / len(events), 3),
        })
    
    # Write frame data
    output = {
        'header': header,
        'fps': fps,
        'totalFrames': total_frames,
        'totalDuration': round(total_duration, 3),
        'eventCount': len(events),
        'frames': frames,
    }
    
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=None)  # Compact JSON
    
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"Generated {total_frames} frames → {output_path} ({size_mb:.1f}MB)")


if __name__ == '__main__':
    cast_file = sys.argv[1] if len(sys.argv) > 1 else 'recordings/demo.cast'
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'remotion/src/cast-data.json'
    fps = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    
    if not os.path.exists(cast_file):
        print(f"Error: {cast_file} not found")
        print("Run 'bash record-demo.sh' first to create the recording")
        sys.exit(1)
    
    process_cast(cast_file, output_file, fps)

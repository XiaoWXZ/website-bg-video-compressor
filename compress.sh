#!/usr/bin/env bash

# macOS bash equivalent of the provided PowerShell script

set -o pipefail

if [ $# -ne 2 ]; then
  echo "usage: $0 <input_file> <target_size_mb>" >&2
  exit 1
fi

input_file="$1"
target_mb="$2"

if ! command -v ffprobe >/dev/null 2>&1; then
  echo "ffprobe not found." >&2
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found." >&2
  exit 1
fi

if [ ! -f "$input_file" ]; then
  echo "input file '$input_file' not found." >&2
  exit 1
fi

duration="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$input_file" 2>/dev/null)"
if [ -z "$duration" ]; then
  echo "unable to retrieve duration from '$input_file'." >&2
  exit 1
fi

# compute target video bitrate (no audio) with 5% container overhead
bitrate_k="$(
  awk -v size_mb="$target_mb" -v dur="$duration" '
    BEGIN {
      bytes_per_mb = 1048576;
      size_bits    = size_mb * bytes_per_mb * 8;
      usable_bits  = size_bits * 0.95;            # subtract 5% overhead
      if (dur <= 0) { print 0; exit }
      bitrate_bps  = int(usable_bits / dur);      # floor
      print int(bitrate_bps / 1024);              # kbits/s
    }'
)"

if [ -z "$bitrate_k" ] || [ "$bitrate_k" -le 0 ]; then
  echo "computed bitrate is invalid." >&2
  exit 1
fi

base_name="$(basename "$input_file")"
base_name="${base_name%.*}"
output_file="${base_name}_compressed.mp4"

ffmpeg -i "$input_file" -c:v libx265 -b:v "${bitrate_k}k" -an -y "$output_file"
exit_code=$?

if [ $exit_code -eq 0 ]; then
  echo "compression complete. output saved as '$output_file' (target: ${target_mb} mb)."
else
  echo "ffmpeg failed with exit code $exit_code." >&2
  exit $exit_code
fi

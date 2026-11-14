// Record N seconds from the default microphone to a 16-bit mono 12 kHz WAV file.
// Usage: rec <out.wav> [seconds]
import AVFoundation

let args = CommandLine.arguments
guard args.count > 1 else { fputs("usage: rec <out.wav> [seconds]\n", stderr); exit(64) }
let seconds = Double(args.count > 2 ? args[2] : "4") ?? 4
let settings: [String: Any] = [
    AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 12000.0, AVNumberOfChannelsKey: 1,
    AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false,
]
let gate = DispatchSemaphore(value: 0)
var granted = false
AVCaptureDevice.requestAccess(for: .audio) { ok in granted = ok; gate.signal() }
gate.wait()
guard granted else { fputs("microphone access was not granted\n", stderr); exit(2) }
let recorder = try AVAudioRecorder(url: URL(fileURLWithPath: args[1]), settings: settings)
guard recorder.record(forDuration: seconds) else { fputs("could not start recording\n", stderr); exit(3) }
Thread.sleep(forTimeInterval: seconds + 0.3)
recorder.stop()

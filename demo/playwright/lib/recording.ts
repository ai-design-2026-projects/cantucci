import * as fs from 'fs'
import * as path from 'path'

export interface Turn {
    user_message: string
    assistant: { content: string; suggestion?: string }
    cluster_snapshot_id: string
}

export interface Recording {
    name: string
    turns: Turn[]
}

export function loadRecording(): Recording {
    const recordingPath = process.env.DEMO_RECORDING
    if (!recordingPath) {
        throw new Error(
            'DEMO_RECORDING env var must point to a recording JSON file.\n' +
            'Example: DEMO_RECORDING=../recordings/my-demo.json npx playwright test --headed',
        )
    }
    const resolved = path.isAbsolute(recordingPath)
        ? recordingPath
        : path.resolve(__dirname, '..', recordingPath)
    return JSON.parse(fs.readFileSync(resolved, 'utf-8')) as Recording
}

/**
 * Custom hook for voice recording and transcription
 * Extracts voice recording logic from Chat component
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { chatAPI } from '../utils/api';

export function useVoiceRecording(onTranscriptionComplete) {
    const [isRecording, setIsRecording] = useState(false);
    const [isTranscribing, setIsTranscribing] = useState(false);

    const mediaRecorderRef = useRef(null);
    const audioChunksRef = useRef([]);
    const abortControllerRef = useRef(null);
    const streamRef = useRef(null);

    // Kills microphone instantly to free resources and remove browser tracking icon
    const cleanupStream = useCallback(() => {
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop());
            streamRef.current = null;
        }
    }, []);

    const cancelTranscription = useCallback(() => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            setIsTranscribing(false);
        }
    }, []);

    const handleTranscription = useCallback(async () => {
        setIsTranscribing(true);
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        abortControllerRef.current = new AbortController();

        try {
            const { data } = await chatAPI.transcribe(audioBlob, abortControllerRef.current.signal);
            if (data?.text) {
                onTranscriptionComplete?.(data.text);
            }
        } catch (error) {
            const isCanceled = ['CanceledError', 'AbortError'].includes(error.name) || error.message === 'canceled';
            if (!isCanceled) {
                console.error('Transcription error:', error);
                alert('Failed to transcribe audio. Please try again.');
            }
        } finally {
            setIsTranscribing(false);
            abortControllerRef.current = null;
        }
    }, [onTranscriptionComplete]);

    const startRecording = useCallback(async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            streamRef.current = stream;
            
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            audioChunksRef.current = [];

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunksRef.current.push(event.data);
                }
            };

            mediaRecorder.onstop = () => {
                cleanupStream(); // Kill mic instantly upon stopping
                handleTranscription();
            };

            mediaRecorder.start();
            setIsRecording(true);
        } catch (error) {
            console.error('Microphone access error:', error);
            alert('Could not access microphone. Please check permissions.');
        }
    }, [cleanupStream, handleTranscription]);

    const stopRecording = useCallback(() => {
        if (mediaRecorderRef.current && isRecording) {
            mediaRecorderRef.current.stop();
            setIsRecording(false);
        }
    }, [isRecording]);

    // Cleanup lingering tracks and requests on unmount
    useEffect(() => {
        return () => {
            cleanupStream();
            cancelTranscription();
        };
    }, [cleanupStream, cancelTranscription]);

    return {
        isRecording,
        isTranscribing,
        startRecording,
        stopRecording,
        cancelTranscription,
    };
}

export default useVoiceRecording;

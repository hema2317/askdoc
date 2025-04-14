import React, { useState } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  ScrollView,
  SafeAreaView,
  Platform,
  KeyboardAvoidingView,
  Alert,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';

export default function App() {
  const [query, setQuery] = useState('');
  const [chatHistory, setChatHistory] = useState([]);

  const handleAsk = () => {
    if (!query.trim()) return;
    const mockAnswer = `Pretend AI answer to: "${query}"`;
    setChatHistory([...chatHistory, { q: query, a: mockAnswer }]);
    setQuery('');
  };

  const handleFilePick = async () => {
    const result = await DocumentPicker.getDocumentAsync({});
    if (result.type === 'success') {
      Alert.alert('File Selected', result.name);
    }
  };

  const handleVoiceInput = async () => {
    try {
      alert('🎤 Voice-to-text not implemented yet.');
    } catch (error) {
      console.error('Voice error:', error);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
        keyboardVerticalOffset={80}
      >
        <Text style={styles.header}>🩺 AskDoc</Text>

        <ScrollView style={styles.chatLog} contentContainerStyle={{ paddingBottom: 80 }}>
          {chatHistory.map((entry, index) => (
            <View key={index} style={styles.message}>
              <Text style={styles.question}>🧠 Q: <Text style={styles.bold}>{entry.q}</Text></Text>
              <Text style={styles.answer}>💬 A: {entry.a}</Text>
            </View>
          ))}
        </ScrollView>

        <View style={styles.inputArea}>
          <TextInput
            style={styles.input}
            value={query}
            onChangeText={setQuery}
            placeholder="Ask a health question..."
            multiline
          />
          <View style={styles.row}>
            <TouchableOpacity onPress={handleVoiceInput} style={styles.button}>
              <Text>🎙 Voice</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={handleFilePick} style={styles.button}>
              <Text>📎 File</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={handleAsk} style={[styles.button, styles.askBtn]}>
              <Text style={{ color: 'white' }}>Ask</Text>
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#eaf6ff',
    paddingHorizontal: 16,
  },
  header: {
    fontSize: 28,
    fontWeight: 'bold',
    textAlign: 'center',
    marginVertical: 16,
    color: '#0084ff',
  },
  chatLog: {
    flex: 1,
    marginBottom: 8,
  },
  message: {
    marginBottom: 16,
    padding: 12,
    backgroundColor: '#fff',
    borderRadius: 12,
    shadowColor: '#000',
    shadowOpacity: 0.1,
    shadowRadius: 5,
    elevation: 2,
  },
  question: {
    fontSize: 16,
    marginBottom: 4,
  },
  answer: {
    fontSize: 15,
    color: '#333',
  },
  bold: {
    fontWeight: 'bold',
  },
  inputArea: {
    paddingVertical: 12,
  },
  input: {
    backgroundColor: '#fff',
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#ccc',
    fontSize: 16,
    marginBottom: 8,
    minHeight: 60,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
  },
  button: {
    flex: 1,
    padding: 10,
    backgroundColor: '#e6f0f7',
    borderRadius: 8,
    alignItems: 'center',
  },
  askBtn: {
    backgroundColor: '#0084ff',
  },
});

// --- START OF FILE supabaseClient.js ---

// supabaseClient.js
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = "https://nlfvwbjpeywcessqyqac.supabase.co";
const supabaseAnonKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5sZnZ3YmpwZXl3Y2Vzc3F5cWFjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDU4NTczNjQsImV4cCI6MjA2MTQzMzM2NH0.zL84P7bK7qHxJt8MtkTPkqNe4U_K512ZgtpPvD9PoRI";
// Define AsyncStorage adapter for Supabase
const CustomAsyncStorage = {
  getItem: async (key) => {
    return AsyncStorage.getItem(key);
  },
  setItem: async (key, value) => {
    return AsyncStorage.setItem(key, value);
  },
  removeItem: async (key) => {
    return AsyncStorage.removeItem(key);
  },
};

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    storage: CustomAsyncStorage, // Use AsyncStorage for session persistence
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false, // Crucial for React Native
  },
});
// --- END OF FILE supabaseClient.js ---
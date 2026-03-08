import React, { useState, useRef, useEffect } from 'react';
import { XMarkIcon, PaperAirplaneIcon, SparklesIcon } from '@heroicons/react/24/outline';

export function AIAssistantChat({ inline = false, theme = 'mce' }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        "Hi! I'm your CAPA cluster assistant. I can help you understand cluster status, troubleshoot issues, or explain CAPA concepts. What would you like to know?",
      timestamp: new Date(),
    },
  ]);

  // Get theme colors
  const getThemeColors = () => {
    switch (theme) {
      case 'minikube':
        return {
          gradient: 'from-purple-50 to-violet-50',
          border: 'border-purple-200',
          text: 'text-purple-900',
          userBg: 'bg-purple-600',
          userBgHover: 'hover:bg-purple-700',
          buttonBg: 'bg-purple-600',
          buttonBgHover: 'hover:bg-purple-700',
          focusRing: 'focus:ring-purple-500 focus:border-purple-500',
          headerGradient: 'from-purple-600 to-violet-600',
        };
      case 'main':
        return {
          gradient: 'from-gray-50 to-gray-100',
          border: 'border-gray-200',
          text: 'text-gray-900',
          userBg: 'bg-gray-600',
          userBgHover: 'hover:bg-gray-700',
          buttonBg: 'bg-gray-600',
          buttonBgHover: 'hover:bg-gray-700',
          focusRing: 'focus:ring-gray-500 focus:border-gray-500',
          headerGradient: 'from-gray-600 to-gray-700',
        };
      case 'mce':
      default:
        return {
          gradient: 'from-blue-50 to-cyan-50',
          border: 'border-blue-200',
          text: 'text-blue-900',
          userBg: 'bg-blue-600',
          userBgHover: 'hover:bg-blue-700',
          buttonBg: 'bg-blue-600',
          buttonBgHover: 'hover:bg-blue-700',
          focusRing: 'focus:ring-blue-500 focus:border-blue-500',
          headerGradient: 'from-blue-600 to-cyan-600',
        };
    }
  };

  const colors = getThemeColors();
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = {
      role: 'user',
      content: input,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      // Get current cluster context
      const clustersResponse = await fetch('http://localhost:8000/api/rosa/clusters');
      const clustersData = await clustersResponse.json();

      // Send to AI assistant endpoint
      const response = await fetch('http://localhost:8000/api/ai-assistant/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: input,
          context: {
            clusters: clustersData.clusters || [],
            history: messages.slice(-5), // Last 5 messages for context
          },
        }),
      });

      const data = await response.json();

      const assistantMessage = {
        role: 'assistant',
        content: data.response,
        timestamp: new Date(),
        suggestions: data.suggestions, // Optional action suggestions
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date(),
        isError: true,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleSuggestionClick = (suggestion) => {
    setInput(suggestion);
  };

  // If inline mode, render without floating button/modal
  if (inline) {
    return (
      <div className="w-full h-[600px] bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2 ${
                  message.role === 'user'
                    ? `${colors.userBg} text-white`
                    : message.isError
                      ? 'bg-red-50 text-red-900 border border-red-200'
                      : index === 0
                        ? `bg-gradient-to-r ${colors.gradient} text-gray-900 shadow-md border-2 ${colors.border}`
                        : 'bg-white text-gray-900 shadow-sm'
                }`}
              >
                {index === 0 && message.role === 'assistant' && (
                  <div className={`flex items-center gap-2 mb-2 pb-2 border-b ${colors.border}`}>
                    <span className="text-2xl">🤖</span>
                    <span className={`font-semibold ${colors.text}`}>Welcome!</span>
                  </div>
                )}
                <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                <p className="text-xs opacity-70 mt-1">
                  {message.timestamp.toLocaleTimeString()}
                </p>

                {/* Action Suggestions */}
                {message.suggestions && message.suggestions.length > 0 && (
                  <div className="mt-3 space-y-2">
                    <p className="text-xs font-semibold opacity-70">Suggested actions:</p>
                    {message.suggestions.map((suggestion, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleSuggestionClick(suggestion)}
                        className="block w-full text-left text-xs bg-white/50 hover:bg-white/80 px-2 py-1 rounded transition-colors"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-white rounded-lg px-4 py-2 shadow-sm">
                <div className="flex gap-1">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick Actions */}
        <div className="px-4 py-2 border-t border-gray-200 bg-white">
          <div className="flex gap-2 overflow-x-auto">
            {[
              'What clusters are running?',
              'Troubleshoot failed cluster',
              'Explain ROSA HCP',
              'How to provision cluster?',
            ].map((quick, idx) => (
              <button
                key={idx}
                onClick={() => setInput(quick)}
                className="px-3 py-1 text-xs bg-gray-100 border border-gray-300 rounded-full hover:bg-gray-200 transition-colors whitespace-nowrap"
              >
                {quick}
              </button>
            ))}
          </div>
        </div>

        {/* Input */}
        <div className="p-4 border-t border-gray-200 bg-white rounded-b-lg">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Ask me anything about your clusters..."
              className={`flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 ${colors.focusRing} resize-none`}
              rows="2"
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || isLoading}
              className={`px-4 py-2 ${colors.buttonBg} text-white rounded-lg ${colors.buttonBgHover} disabled:opacity-50 disabled:cursor-not-allowed transition-colors`}
            >
              <PaperAirplaneIcon className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Original floating chat widget mode
  return (
    <>
      {/* Floating Chat Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className={`fixed bottom-6 right-6 bg-gradient-to-r ${colors.headerGradient} text-white p-4 rounded-full shadow-lg hover:shadow-xl transform hover:scale-110 transition-all duration-200`}
          style={{ zIndex: 9999 }}
        >
          <SparklesIcon className="h-6 w-6" />
        </button>
      )}

      {/* Chat Window */}
      {isOpen && (
        <div
          className="fixed bottom-6 right-6 w-96 h-[600px] bg-white rounded-lg shadow-2xl flex flex-col border border-gray-200"
          style={{ zIndex: 9999 }}
        >
          {/* Header */}
          <div className={`bg-gradient-to-r ${colors.headerGradient} text-white px-4 py-3 rounded-t-lg flex items-center justify-between`}>
            <div className="flex items-center gap-2">
              <SparklesIcon className="h-5 w-5" />
              <h3 className="font-semibold">AI Assistant</h3>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="hover:bg-white/20 rounded p-1 transition-colors"
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((message, index) => (
              <div
                key={index}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-2 ${
                    message.role === 'user'
                      ? `${colors.userBg} text-white`
                      : message.isError
                        ? 'bg-red-50 text-red-900 border border-red-200'
                        : index === 0
                          ? `bg-gradient-to-r ${colors.gradient} text-gray-900 shadow-md border-2 ${colors.border}`
                          : 'bg-gray-100 text-gray-900'
                  }`}
                >
                  {index === 0 && message.role === 'assistant' && (
                    <div className={`flex items-center gap-2 mb-2 pb-2 border-b ${colors.border}`}>
                      <span className="text-2xl">🤖</span>
                      <span className={`font-semibold ${colors.text}`}>Welcome!</span>
                    </div>
                  )}
                  <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                  <p className="text-xs opacity-70 mt-1">
                    {message.timestamp.toLocaleTimeString()}
                  </p>

                  {/* Action Suggestions */}
                  {message.suggestions && message.suggestions.length > 0 && (
                    <div className="mt-3 space-y-2">
                      <p className="text-xs font-semibold opacity-70">Suggested actions:</p>
                      {message.suggestions.map((suggestion, idx) => (
                        <button
                          key={idx}
                          onClick={() => handleSuggestionClick(suggestion)}
                          className="block w-full text-left text-xs bg-white/50 hover:bg-white/80 px-2 py-1 rounded transition-colors"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-gray-100 rounded-lg px-4 py-2">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Quick Actions */}
          <div className="px-4 py-2 border-t border-gray-200 bg-gray-50">
            <div className="flex gap-2 overflow-x-auto">
              {[
                'What clusters are running?',
                'Troubleshoot failed cluster',
                'Explain ROSA HCP',
                'How to provision cluster?',
              ].map((quick, idx) => (
                <button
                  key={idx}
                  onClick={() => setInput(quick)}
                  className="px-3 py-1 text-xs bg-white border border-gray-300 rounded-full hover:bg-gray-100 transition-colors whitespace-nowrap"
                >
                  {quick}
                </button>
              ))}
            </div>
          </div>

          {/* Input */}
          <div className="p-4 border-t border-gray-200">
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Ask me anything about your clusters..."
                className={`flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 ${colors.focusRing} resize-none`}
                rows="2"
              />
              <button
                onClick={sendMessage}
                disabled={!input.trim() || isLoading}
                className={`px-4 py-2 ${colors.buttonBg} text-white rounded-lg ${colors.buttonBgHover} disabled:opacity-50 disabled:cursor-not-allowed transition-colors`}
              >
                <PaperAirplaneIcon className="h-5 w-5" />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

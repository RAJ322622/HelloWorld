module.exports = {
  JWT_SECRET: process.env.JWT_SECRET || 'your_strong_secret_key_here',
  JWT_ACCESS_EXPIRY: '15m',  // Short-lived access token
  JWT_REFRESH_EXPIRY: '7d',  // Longer-lived refresh token
  NODE_ENV: process.env.NODE_ENV || 'development',
  
  // For token blacklisting
  TOKEN_TYPES: {
    ACCESS: 'access',
    REFRESH: 'refresh'
  }
};

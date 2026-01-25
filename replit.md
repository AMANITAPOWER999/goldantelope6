# Goldantelope ASIA

### Overview
Goldantelope ASIA is an automated content parser for Telegram channels and groups in Southeast Asia, focused on providing a visual dashboard and cloud storage for listings. The project aims to offer a comprehensive platform for finding local information and services across various categories in key Asian markets. It supports countries like Vietnam, Thailand, India, and Indonesia, aggregating content ranging from restaurants and real estate to transportation and community chats. The platform provides real-time statistics, filtering capabilities, and an administrative panel for content management, aiming to deliver clean, relevant, and localized information to its users.

### User Preferences
- I prefer clear and concise communication.
- I need detailed explanations for complex features.
- I value iterative development with frequent updates.
- Please ask for confirmation before making significant changes to core logic or architecture.
- I expect the agent to maintain the established white dashboard design with the gold accent (#d4af37).
- Ensure all content displayed is localized and relevant, strictly excluding English-only content and spam.
- Prioritize stable and reliable parsing operations, even if it means a less aggressive approach to API requests.

### System Architecture

#### UI/UX Decisions
- **Dashboard Design**: White background with a professional aesthetic, using a gold accent color (#d4af37).
- **Interactive Elements**: Visual city switching for categories like Restaurants, Tours, and Entertainment in Vietnam, with photo support for 10 cities.
- **Filtering**: Advanced filters for content categories (e.g., transport by model, year, price; real estate by rooms, location, price).
- **Admin Panel**: Integrated administrative tools with a clear, user-friendly interface for content and channel management, including a prominent red "⚙️ Admin" button.
- **Content Editing Modals**: Specialized modal windows for editing listings across all categories, supporting up to 4 photos and comprehensive field sets (e.g., property type, cuisine, engine volume).

#### Technical Implementations
- **Frontend**: Flask application serving HTML/CSS/JS dashboard on port 5000.
- **Backend API**: RESTful API supporting country selection for data retrieval and administrative functions.
- **Data Storage**: Listings are stored in country-specific JSON files (e.g., `listings_vietnam.json`).
- **CDN Integration**: Bunny.net is used for storing real photos extracted from Telegram.
- **Real-time Updates**: Chat content is updated automatically every minute.
- **Telegram Photo Storage**: Approved photos are uploaded to a dedicated Telegram channel for archival.
- **Internal Chat**: Features a community chat with Telegram ID authorization and a moderation blacklist managed via the admin panel.

#### Feature Specifications
- **Content Categories**: 11 distinct content categories with tailored filtering options.
- **Real-time Statistics**: Dashboard displays live statistics by category.
- **Direct Telegram Links**: Listings include direct links back to their original Telegram posts.
- **Admin Panel Capabilities**:
    - Secure password-based authorization.
    - Delete and move listings between categories.
    - Manage Telegram channels (add/remove by country and category).
    - Manage cities (add/edit/delete with photos for all categories).
    - Manual parser function for specific channels with category selection.
- **Multi-session Parsing**: Utilizes dual Telegram sessions (`goldantelope_user` and `goldantelope_additional`) for concurrent parsing to mitigate rate limits.
- **Spam and Language Filtering**: Automated rejection of English-only content, spam, and promotional material across all parsers.
- **Rate Limit Strategy**: Less aggressive parsing with reduced message fetches per channel and increased delays to ensure stable operation.

#### System Design Choices
- **Modularity**: Data is stored separately for each supported country.
- **Scalability**: Designed with separate parsers and API endpoints to manage different types of data and administrative tasks.
- **Resilience**: Dual parsing system and rate limit management designed to prevent service interruptions from Telegram API restrictions.

### External Dependencies
- **Telegram Bot API**: For parsing content from Telegram channels and groups, community chat features, and photo storage.
- **Bunny.net CDN**: For hosting and serving real photos extracted from Telegram.
- **Flask**: Python web framework for the frontend dashboard and API.
- **JSON Files**: Used as the primary data storage mechanism for listings.
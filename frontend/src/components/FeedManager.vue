<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ readOnly: { type: Boolean, default: false } })

const feeds = ref([])
const loading = ref(false)
const newFeedUrl = ref('')
const newFeedName = ref('')
const validationResult = ref(null)
const validationLoading = ref(false)
const showAddForm = ref(false)
const successMessage = ref('')
const errorMessage = ref('')

// Load feeds on mount
async function loadFeeds() {
  loading.value = true
  try {
    const res = await fetch('/api/feeds')
    feeds.value = await res.json()
  } catch (e) {
    errorMessage.value = `Failed to load feeds: ${e.message}`
  } finally {
    loading.value = false
  }
}

// Validate feed URL in real-time
async function validateFeed() {
  if (!newFeedUrl.value) {
    validationResult.value = null
    return
  }

  validationLoading.value = true
  try {
    const res = await fetch('/api/feeds/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: newFeedUrl.value, name: newFeedName.value || undefined })
    })
    validationResult.value = await res.json()
  } catch (e) {
    validationResult.value = {
      valid: false,
      errors: [`Failed to validate feed: ${e.message}`]
    }
  } finally {
    validationLoading.value = false
  }
}

// Add new feed
async function addFeed() {
  if (!validationResult.value?.valid) {
    errorMessage.value = 'Feed validation failed. Check errors above.'
    return
  }

  loading.value = true
  try {
    const res = await fetch('/api/feeds', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: newFeedUrl.value,
        name: newFeedName.value || validationResult.value.feed_type
      })
    })

    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Failed to add feed')
    }

    successMessage.value = 'Feed added successfully!'
    newFeedUrl.value = ''
    newFeedName.value = ''
    validationResult.value = null
    showAddForm.value = false

    await loadFeeds()

    setTimeout(() => { successMessage.value = '' }, 3000)
  } catch (e) {
    errorMessage.value = e.message
  } finally {
    loading.value = false
  }
}

// Delete feed
async function deleteFeed(feedId) {
  if (!confirm('Are you sure you want to delete this feed?')) return

  try {
    const res = await fetch(`/api/feeds/${feedId}`, { method: 'DELETE' })
    if (!res.ok) throw new Error('Failed to delete')

    successMessage.value = 'Feed deleted'
    await loadFeeds()
    setTimeout(() => { successMessage.value = '' }, 2000)
  } catch (e) {
    errorMessage.value = e.message
  }
}

// Toggle feed active status
async function toggleFeed(feedId, currentActive) {
  try {
    const res = await fetch(`/api/feeds/${feedId}?active=${!currentActive}`, {
      method: 'PATCH'
    })
    if (!res.ok) throw new Error('Failed to toggle')

    successMessage.value = 'Feed updated'
    await loadFeeds()
    setTimeout(() => { successMessage.value = '' }, 2000)
  } catch (e) {
    errorMessage.value = e.message
  }
}

// Load feeds on component mount
loadFeeds()

// Computed properties
const canAddFeed = computed(() => validationResult.value?.valid === true)
const hasErrors = computed(() => validationResult.value?.errors?.length > 0)
</script>

<template>
  <div class="feed-manager">
    <div class="header">
      <h2>RSS Feed Management</h2>
      <span v-if="readOnly" class="read-only-badge" title="This instance is in read-only mode. Feed management is disabled.">Read-only</span>
      <button v-if="!showAddForm && !readOnly" class="btn-add" @click="showAddForm = true">
        + Add Feed
      </button>
    </div>

    <!-- Messages -->
    <div v-if="successMessage" class="message success">
      {{ successMessage }}
    </div>
    <div v-if="errorMessage" class="message error">
      {{ errorMessage }}
    </div>

    <!-- Add Feed Form -->
    <div v-if="showAddForm" class="add-form">
      <div class="form-group">
        <label>Feed URL</label>
        <input
          v-model="newFeedUrl"
          type="url"
          placeholder="https://..."
          @input="validateFeed"
          class="input-url"
        />
      </div>

      <div class="form-group">
        <label>Feed Name (optional)</label>
        <input
          v-model="newFeedName"
          type="text"
          placeholder="e.g., My Financial News"
          class="input-name"
        />
      </div>

      <!-- Validation Result -->
      <div v-if="validationLoading" class="validation-loading">
        Testing feed...
      </div>

      <div v-if="validationResult && !validationLoading" class="validation-result">
        <div v-if="validationResult.valid" class="valid-badge">
          ✅ Valid {{ validationResult.feed_type }}
        </div>
        <div v-else class="invalid-badge">
          ❌ Invalid Feed
        </div>

        <div class="details">
          <div class="detail-row">
            <span class="label">Feed Type:</span>
            <span class="value">{{ validationResult.feed_type || 'Unknown' }}</span>
          </div>
          <div class="detail-row">
            <span class="label">Entries Found:</span>
            <span class="value">{{ validationResult.entry_count }}</span>
          </div>

          <div v-if="validationResult.sample_entries?.length" class="samples">
            <div class="sample-title">Sample Entries:</div>
            <div v-for="(entry, i) in validationResult.sample_entries" :key="i" class="sample">
              <div class="sample-text">{{ entry.title }}</div>
              <div class="sample-meta">
                Summary: {{ entry.summary_length }} chars •
                Timestamp: {{ entry.has_timestamp ? '✅' : '❌' }}
              </div>
            </div>
          </div>

          <div v-if="validationResult.errors?.length" class="errors">
            <div class="error-title">Issues:</div>
            <div v-for="(err, i) in validationResult.errors" :key="i" class="error-item">
              ⚠️ {{ err }}
            </div>
          </div>

          <div v-if="validationResult.warnings?.length" class="warnings">
            <div class="warning-title">Warnings:</div>
            <div v-for="(warn, i) in validationResult.warnings" :key="i" class="warning-item">
              ℹ️ {{ warn }}
            </div>
          </div>
        </div>

        <div class="form-actions">
          <button
            v-if="canAddFeed"
            @click="addFeed"
            class="btn btn-primary"
            :disabled="loading"
          >
            {{ loading ? 'Adding...' : 'Add Feed' }}
          </button>
          <button @click="showAddForm = false" class="btn btn-secondary">
            Cancel
          </button>
        </div>
      </div>

      <div v-if="!validationResult && newFeedUrl && !validationLoading" class="placeholder">
        Enter a valid feed URL above
      </div>
    </div>

    <!-- Feeds List -->
    <div v-if="!showAddForm" class="feeds-list">
      <div v-if="loading" class="loading">Loading feeds...</div>

      <div v-if="feeds.length === 0 && !loading" class="empty">
        No feeds configured. Add one to get started.
      </div>

      <div v-for="feed in feeds" :key="feed.id" class="feed-card">
        <div class="feed-header">
          <div class="feed-title">
            <h3>{{ feed.name }}</h3>
            <span class="feed-type">{{ feed.feed_type }}</span>
          </div>
          <div class="feed-actions">
            <button
              @click="!readOnly && toggleFeed(feed.id, feed.active)"
              :class="['btn-toggle', feed.active ? 'active' : 'inactive', { disabled: readOnly }]"
              :title="readOnly ? 'Read-only mode' : ''"
            >
              {{ feed.active ? '✓ Active' : '○ Inactive' }}
            </button>
            <button
              v-if="!readOnly"
              @click="deleteFeed(feed.id)"
              class="btn-delete"
            >
              Delete
            </button>
          </div>
        </div>

        <div class="feed-url">
          <small>{{ feed.url }}</small>
        </div>

        <div class="feed-meta">
          <small>Added: {{ new Date(feed.added_at).toLocaleDateString() }}</small>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.feed-manager {
  padding: 20px;
  max-width: 900px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  border-bottom: 1px solid #222;
  padding-bottom: 16px;
}

.header h2 {
  font-size: 1.5rem;
  color: #e0e0e0;
  margin: 0;
}

.read-only-badge {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #888;
  background: #222;
  border: 1px solid #444;
  border-radius: 4px;
  padding: 4px 10px;
  cursor: default;
}

.btn-toggle.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-add {
  padding: 8px 16px;
  background: #3a7d5a;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  transition: background 0.2s;
}

.btn-add:hover {
  background: #2a6545;
}

/* Messages */
.message {
  padding: 12px 16px;
  border-radius: 4px;
  margin-bottom: 16px;
  font-size: 0.9rem;
}

.message.success {
  background: #1e3a2a;
  color: #7dd3a0;
  border-left: 3px solid #3a7d5a;
}

.message.error {
  background: #3a1e1e;
  color: #e08080;
  border-left: 3px solid #a05060;
}

/* Add Form */
.add-form {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 20px;
  margin-bottom: 24px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 0.85rem;
  font-weight: 600;
  color: #aaa;
  margin-bottom: 6px;
}

.input-url,
.input-name {
  width: 100%;
  padding: 10px 12px;
  background: #0d0d0d;
  border: 1px solid #333;
  border-radius: 4px;
  color: #e0e0e0;
  font-family: monospace;
  font-size: 0.9rem;
}

.input-url:focus,
.input-name:focus {
  outline: none;
  border-color: #3a7d5a;
  box-shadow: 0 0 0 2px rgba(58, 125, 90, 0.1);
}

.validation-loading {
  text-align: center;
  padding: 20px;
  color: #888;
  font-size: 0.9rem;
}

.validation-result {
  background: #0d0d0d;
  border: 1px solid #222;
  border-radius: 4px;
  padding: 16px;
  margin-top: 16px;
}

.valid-badge,
.invalid-badge {
  font-weight: 600;
  margin-bottom: 12px;
  font-size: 0.95rem;
}

.valid-badge {
  color: #7dd3a0;
}

.invalid-badge {
  color: #e08080;
}

.details {
  margin-top: 12px;
}

.detail-row {
  display: flex;
  padding: 8px 0;
  font-size: 0.85rem;
  border-bottom: 1px solid #222;
}

.detail-row .label {
  color: #888;
  min-width: 120px;
}

.detail-row .value {
  color: #e0e0e0;
}

.samples {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #222;
}

.sample-title {
  font-size: 0.8rem;
  color: #888;
  font-weight: 600;
  margin-bottom: 8px;
}

.sample {
  background: #111;
  border: 1px solid #1e1e1e;
  border-radius: 3px;
  padding: 8px;
  margin-bottom: 6px;
  font-size: 0.8rem;
}

.sample-text {
  color: #e0e0e0;
  margin-bottom: 4px;
}

.sample-meta {
  color: #666;
  font-size: 0.75rem;
}

.errors {
  margin-top: 12px;
  padding: 8px;
  background: #2a1a1a;
  border-radius: 3px;
  border-left: 3px solid #a05060;
}

.error-title {
  font-size: 0.8rem;
  color: #e08080;
  font-weight: 600;
  margin-bottom: 6px;
}

.error-item {
  font-size: 0.8rem;
  color: #e08080;
  margin-bottom: 3px;
}

.warnings {
  margin-top: 12px;
  padding: 8px;
  background: #2a2a1a;
  border-radius: 3px;
  border-left: 3px solid #e0a832;
}

.warning-title {
  font-size: 0.8rem;
  color: #e0a832;
  font-weight: 600;
  margin-bottom: 6px;
}

.warning-item {
  font-size: 0.8rem;
  color: #e0a832;
  margin-bottom: 3px;
}

.form-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

.btn {
  padding: 10px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  transition: opacity 0.2s;
}

.btn-primary {
  background: #3a7d5a;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #2a6545;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: #333;
  color: #e0e0e0;
}

.btn-secondary:hover {
  background: #444;
}

.placeholder {
  padding: 16px;
  text-align: center;
  color: #666;
  font-size: 0.9rem;
}

/* Feeds List */
.feeds-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.loading {
  text-align: center;
  padding: 20px;
  color: #888;
}

.empty {
  text-align: center;
  padding: 40px 20px;
  color: #666;
}

.feed-card {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.feed-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.feed-title {
  flex: 1;
}

.feed-title h3 {
  margin: 0;
  font-size: 1rem;
  color: #e0e0e0;
}

.feed-type {
  display: inline-block;
  background: #222;
  color: #888;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 0.75rem;
  margin-top: 4px;
}

.feed-actions {
  display: flex;
  gap: 8px;
}

.btn-toggle,
.btn-delete {
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;
  transition: opacity 0.2s;
}

.btn-toggle.active {
  background: #1e3a2a;
  color: #7dd3a0;
}

.btn-toggle.inactive {
  background: #2a1a1a;
  color: #e08080;
}

.btn-delete {
  background: #3a1e1e;
  color: #e08080;
}

.btn-delete:hover {
  opacity: 0.8;
}

.feed-url {
  word-break: break-all;
  color: #666;
}

.feed-url small {
  font-size: 0.8rem;
  font-family: monospace;
}

.feed-meta {
  color: #555;
  font-size: 0.75rem;
}
</style>

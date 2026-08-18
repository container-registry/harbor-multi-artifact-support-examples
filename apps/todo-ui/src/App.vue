<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import * as api from './api.js'

import TodoHeader from './components/TodoHeader.vue'
import TodoItem from './components/TodoItem.vue'
import TodoFooter from './components/TodoFooter.vue'

const todos = ref([])
const error = ref('')
const filter = ref(filterFromHash())

function filterFromHash() {
  const name = window.location.hash.replace(/^#\/?/, '')
  return ['active', 'completed'].includes(name) ? name : 'all'
}

function onHashChange() {
  filter.value = filterFromHash()
}

onMounted(() => {
  window.addEventListener('hashchange', onHashChange)
  load()
})
onUnmounted(() => window.removeEventListener('hashchange', onHashChange))

// Every mutation round-trips through the API, so a failure must not leave the
// list showing state the server never accepted; reload instead of patching.
async function run(fn) {
  try {
    await fn()
    error.value = ''
  } catch (e) {
    error.value = e.message
    await load()
  }
}

async function load() {
  try {
    todos.value = await api.listTodos()
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
}

const activeTodos = computed(() => todos.value.filter((todo) => !todo.completed))
const completedTodos = computed(() => todos.value.filter((todo) => todo.completed))
const filteredTodos = computed(() => {
  switch (filter.value) {
    case 'active':
      return activeTodos.value
    case 'completed':
      return completedTodos.value
    default:
      return todos.value
  }
})

const toggleAllModel = computed({
  get() {
    return todos.value.length > 0 && activeTodos.value.length === 0
  },
  set(value) {
    toggleAll(value)
  },
})

function addTodo(title) {
  run(async () => {
    todos.value = [...todos.value, await api.createTodo(title)]
  })
}

function deleteTodo(todo) {
  run(async () => {
    await api.removeTodo(todo.id)
    todos.value = todos.value.filter((t) => t.id !== todo.id)
  })
}

function toggleTodo(todo, completed) {
  run(async () => {
    replace(await api.updateTodo(todo.id, { completed }))
  })
}

function editTodo(todo, title) {
  run(async () => {
    replace(await api.updateTodo(todo.id, { title }))
  })
}

function toggleAll(completed) {
  run(async () => {
    const changed = todos.value.filter((todo) => todo.completed !== completed)
    const updated = await Promise.all(changed.map((todo) => api.updateTodo(todo.id, { completed })))
    updated.forEach(replace)
  })
}

function deleteCompleted() {
  run(async () => {
    await api.clearCompleted()
    todos.value = todos.value.filter((todo) => !todo.completed)
  })
}

function replace(updated) {
  todos.value = todos.value.map((todo) => (todo.id === updated.id ? updated : todo))
}
</script>

<template>
  <TodoHeader @add-todo="addTodo" />
  <main class="main" v-show="todos.length > 0">
    <div class="toggle-all-container">
      <input
        type="checkbox"
        id="toggle-all-input"
        class="toggle-all"
        v-model="toggleAllModel"
        :disabled="todos.length === 0"
      />
      <label class="toggle-all-label" for="toggle-all-input"> Toggle All Input </label>
    </div>
    <ul class="todo-list">
      <TodoItem
        v-for="todo in filteredTodos"
        :key="todo.id"
        :todo="todo"
        @delete-todo="deleteTodo"
        @edit-todo="editTodo"
        @toggle-todo="toggleTodo"
      />
    </ul>
  </main>
  <TodoFooter :todos="todos" :filter="filter" @delete-completed="deleteCompleted" />
  <p v-if="error" class="api-error">API error: {{ error }}</p>
</template>

<style>
.api-error {
  margin: 1rem auto;
  max-width: 550px;
  color: #af5b5e;
  text-align: center;
}
</style>

<script setup>
const emit = defineEmits(['add-todo'])

function onEnter(event) {
  const text = event.target.value.trim()
  if (text.length === 0) return
  emit('add-todo', text)
  event.target.value = ''
}
</script>

<template>
  <header class="header">
    <a href="#/"><h1>todos</h1></a>
    <input
      type="text"
      class="new-todo"
      autofocus
      autocomplete="off"
      placeholder="What needs to be done?"
      @keyup.enter="onEnter"
    />
  </header>
</template>

class Solution:
  def search(self, arr, target_sum):
    # TODO: Write your code here
    end = len(arr) - 1
    start = 0
    while start != end:
      current_sum = arr[start] + arr[end]
      if current_sum == target_sum:
        return [start, end]
      elif current_sum < target_sum:
        start +=1
      else:
        end -= 1
    return [-1, -1]
